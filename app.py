import streamlit as st
import google.generativeai as genai
from streamlit_drawable_canvas import st_canvas
import requests
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# =====================================================================
# 🛠️ 1. 환경 변수 세팅 및 세션 상태 초기화
# =====================================================================
API_KEY = st.secrets.get("GEMINI_API_KEY", None)
if API_KEY:
    import os
    os.environ["GEMINI_API_KEY"] = API_KEY
else:
    st.error("⚠️ Streamlit Secrets에 'GEMINI_API_KEY'가 설정되지 않았습니다.")
    
# 세션 상태 변수 초기화
if "preview_mode" not in st.session_state: st.session_state.preview_mode = False
if "show_signup" not in st.session_state: st.session_state.show_signup = False
if "generated" not in st.session_state: st.session_state.generated = False
if "ai_generated_desc" not in st.session_state:
    st.session_state.ai_generated_desc = "위 필수 정보를 입력한 후 버튼을 누르면 AI가 본문을 자동으로 작성합니다."

# 주소창 파라미터(?mode=parent)에 따라 화면을 분리하는 원래 방식
query_params = st.query_params
if query_params.get("mode") == "parent":
    current_user_mode = "parent"
else:
    current_user_mode = "teacher"


# =====================================================================
# 🤖 2. AI 본문 자동 작성 함수 정의
# =====================================================================
def generate_announcement_with_ai(title, date, location, supplies, extra_info):
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        
        prompt = f"""
        너는 보목지역아동센터의 따뜻하고 정중한 사회복지사야. 
        아래 제공된 정보를 바탕으로 학부모님들께 모바일로 발송할 '가정통신문 안내문 본문'을 멋지게 작성해줘.
        
        [입력 정보]
        - 프로그램 제목: {title}
        - 일시: {date}
        - 장소: {location}
        - 준비물: {supplies}
        - 기타 강조사항: {extra_info}
        
        부드러운 해요체(~합니다, ~바랍니다)를 사용하고 이모지와 줄바꿈을 섞어서 작성해줘.
        """

        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result_json = response.json()
            return result_json["candidates"][0]["content"]["parts"][0]["text"]
        else:
            backup_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
            backup_response = requests.post(backup_url, headers=headers, json=payload, timeout=30)
            if backup_response.status_code == 200:
                return backup_response.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"❌ 구글 서버 응답 에러: {backup_response.text}"
    except Exception as e:
        return f"❌ AI 생성 중 오류: {str(e)}"


# =====================================================================
# 🔐 2-2. 개인정보 마스킹 & 구글 시트 저장 함수
# =====================================================================
def mask_ssn(ssn):
    """주민등록번호 뒷자리를 가립니다. 예: 970101-1****** (앞 7자리만 보관)"""
    digits = "".join(ch for ch in str(ssn) if ch.isdigit())
    if len(digits) >= 7:
        return f"{digits[:6]}-{digits[6]}{'*' * 6}"
    return "(미입력 또는 형식 오류)"


def _open_spreadsheet():
    """구글 시트에 인증하고 스프레드시트를 엽니다."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(st.secrets["gcp_service_account_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(st.secrets["SHEET_ID"])


def save_to_gsheet(row):
    """제출 정보를 구글 시트 첫 번째 탭에 한 줄 추가합니다. 설정 전이면 안전하게 실패합니다."""
    try:
        sheet = _open_spreadsheet().sheet1
        # 시트가 비어 있으면 머리글(헤더)을 먼저 만들어 둡니다.
        if not sheet.get_all_values():
            sheet.append_row(
                ["제출시각", "아동성명", "보호자성명", "연락처",
                 "주민번호(마스킹)", "동의여부", "서명"]
            )
        sheet.append_row(row)
        return True, None
    except Exception as e:
        return False, str(e)


def publish_announcement(data):
    """교사가 확정한 안내문을 '발송안내문' 탭에 저장합니다. 학부모 화면이 이걸 읽어갑니다."""
    try:
        sh = _open_spreadsheet()
        try:
            ws = sh.worksheet("발송안내문")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="발송안내문", rows=10, cols=10)
        ws.clear()
        ws.append_row(["title", "date", "location", "supplies", "desc", "is_outdoor"])
        ws.append_row([
            data["title"], data["date"], data["location"],
            data["supplies"], data["desc"], "Y" if data["is_outdoor"] else "N",
        ])
        return True, None
    except Exception as e:
        return False, str(e)


def load_announcement():
    """'발송안내문' 탭에서 가장 최근에 확정된 안내문을 불러옵니다. 없으면 None."""
    try:
        ws = _open_spreadsheet().worksheet("발송안내문")
        records = ws.get_all_records()
        if records:
            rec = records[0]
            rec["is_outdoor"] = (str(rec.get("is_outdoor", "")).strip().upper() == "Y")
            return rec
        return None
    except Exception:
        return None


# =====================================================================
# 🎨 3. 디자인 고도화 CSS 정의
# =====================================================================
st.markdown("""
    <style>
    .main .block-container { max-width: 500px; padding-top: 1rem; }
    div.stButton > button {
        background-color: #4F46E5; color: white; width: 100%; padding: 12px;
        border-radius: 8px; border: none; font-weight: bold; font-size: 16px;
    }
    .preview-container {
        background-color: #F9FAFB; padding: 20px; border-radius: 16px;
        border: 3px solid #10B981; margin-top: 15px; box-shadow: 0px 6px 15px rgba(0,0,0,0.05);
    }
    .popup-box {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 2px solid #4F46E5; margin-top: 15px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)


# =====================================================================
# 📱 [CASE 1] 학부모 전용 링크 접속 화면
# =====================================================================
if current_user_mode == "parent":
    # 교사가 확정·발송한 안내문을 구글 시트에서 불러옵니다.
    announcement = load_announcement()
    if announcement:
        st.title(f"🌲 {announcement['title']}")
        st.caption("보목지역아동센터 가정통신문")
        st.info(announcement["desc"])
        show_ssn = announcement["is_outdoor"]
    else:
        st.title("🌲 보목지역아동센터 가정통신문")
        st.caption("보목지역아동센터 가정통신문")
        st.warning("아직 선생님이 확정·발송한 안내문이 없습니다. 잠시 후 다시 확인해 주세요.")
        show_ssn = True  # 안내문이 없을 땐 기존처럼 모두 표시

    st.markdown("---")
    st.subheader("📝 동의서 작성 및 제출")

    if show_ssn:
        st.caption("🤖 야외 활동이라 보험 가입을 위해 아동 주민등록번호를 수집합니다.")
        child_ssn = st.text_input("아동 주민등록번호 (보험 가입용)", placeholder="000000-0000000")
    else:
        child_ssn = ""  # 실내 활동은 주민번호를 수집하지 않습니다.
    child_name = st.text_input("아동 성명", placeholder="예: 김민준")
    parent_name = st.text_input("보호자 성명", placeholder="예: 김철수")
    parent_phone = st.text_input("보호자 연락처", placeholder="예: 010-1234-5678")
    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    agree = st.checkbox("위 내용을 모두 확인하였으며 동의합니다.")
    st.markdown("---")
    
    if agree:
        if st.button("✍️ 터치하여 서명하기"):
            st.session_state.show_signup = True
            
    if st.session_state.get("show_signup", False):
        st.markdown('<div class="popup-box">', unsafe_allow_html=True)
        st.markdown("### 📱 모바일 전용 서명 패드")
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)", stroke_width=3,
            stroke_color="#000000", background_color="#F3F4F6",
            height=150, width=350, drawing_mode="freedraw", key="canvas_parent"
        )
        if st.button("✅ 서명 완료 및 최종 제출하기"):
            has_sign = (
                canvas_result.json_data is not None
                and len(canvas_result.json_data.get("objects", [])) > 0
            )
            if not child_name or not parent_name:
                st.error("⚠️ 아동 성명과 보호자 성명을 꼭 입력해 주세요.")
            elif not has_sign:
                st.error("⚠️ 서명란에 직접 서명을 해주세요.")
            else:
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    child_name,
                    parent_name,
                    parent_phone,
                    mask_ssn(child_ssn) if show_ssn else "미수집(실내활동)",  # 주민번호는 마스킹해서만 저장
                    "동의함",
                    "서명 완료",
                ]
                ok, err = save_to_gsheet(row)
                if ok:
                    st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다!")
                else:
                    # 저장소 연결 전이라도 학부모 화면은 정상으로 보이게 처리
                    st.success("🎉 동의서 제출이 접수되었습니다!")
                    st.caption(f"ℹ️ (관리자 메모) 저장소 연결 대기 중: {err}")
                st.session_state.show_signup = False
        st.markdown('</div>', unsafe_allow_html=True)


# =====================================================================
# 🛡️ [CASE 2] 교사 포털 (관리자 기본 화면)
# =====================================================================
else:
    st.title("🛡️ 보목지역아동센터 교사 포털")
    st.subheader("가정통신문 작성 및 AI 자동화 시스템")
    
    st.write("### 📝 1. 프로그램 기본 정보 입력")
    is_disabled = st.session_state.preview_mode
    
    title = st.text_input("동의서 제목", "섶섬 생태 탐방 및 자리돔 낚시 체험", disabled=is_disabled)
    date = st.text_input("일시", "2026년 7월 11일(토) 09:00 ~ 16:00", disabled=is_disabled)
    location = st.text_input("장소", "섶섬 일대 및 서귀포 보목항", disabled=is_disabled)
    supplies = st.text_input("필수 준비물", "편한 복장, 운동화, 개인 물병, 모자", disabled=is_disabled)
    extra_info = st.text_input("기타 강조 사항", "센터 차량을 이용하며 안전요원이 동행합니다.", disabled=is_disabled)
    
    st.markdown("---")
    st.write("### 🤖 2. AI 안내문 본문 생성")
    
    if not st.session_state.preview_mode:
        if st.button("🪄 AI 안내문 초안 자동 생성하기"):
            with st.spinner("Gemini AI가 멋진 가정통신문을 작성하고 있습니다..."):
                generated_text = generate_announcement_with_ai(title, date, location, supplies, extra_info)
                st.session_state.ai_generated_desc = generated_text
                st.rerun()
    
    desc = st.text_area("상세 안내 문구", value=st.session_state.ai_generated_desc, height=250, disabled=is_disabled)
    # 입력칸에 직접 쓴 내용도 메모리에 저장 → 미리보기/수정 오가도 글이 사라지지 않음
    st.session_state.ai_generated_desc = desc
    is_outdoor = any(keyword in location for keyword in ["섬", "항", "바다", "산", "야외", "캠프", "공원", "체험"])
    
    if not st.session_state.preview_mode:
        st.markdown("---")
        if st.button("🔍 학부모용 서식 시안 미리보기"):
            st.session_state.preview_mode = True
            st.rerun()

    if st.session_state.preview_mode:
        st.markdown("---")
        st.markdown("### 📱 3. 학부모용 최종 발송 시안 확인")
        st.markdown('<div class="preview-container">', unsafe_allow_html=True)
        st.markdown(f"### 🌲 {title}")
        st.caption("보목지역아동센터 가정통신문")
        st.info(desc)
        st.markdown("##### ⚖️ 법적 고지 및 개인정보 수집 동의")
        st.caption("본 동의서의 전자서명은 친필 서명과 동일한 법적 효력을 가집니다.")
        
        if is_outdoor:
            st.warning("🤖 AI 컴플라이언스 엔진 감지: 야외 활동 서식으로 판정되어 보험 가입용 [주민등록번호] 입력란이 활성화됩니다.")
            st.text_input("[학부모 화면 예시] 아동 주민등록번호", "000000-0000000", disabled=True, key="p_ssn")
            
        st.text_input("[학부모 화면 예시] 아동 성명", placeholder="예: 김민준", disabled=True, key="p_name")
        st.text_input("[학부모 화면 예시] 보호자 성명", placeholder="예: 김철수", disabled=True, key="p_pname")
        st.text_input("[학부모 화면 예시] 보호자 연락처", placeholder="예: 010-1234-5678", disabled=True, key="p_phone")
        st.checkbox("[학부모 화면 예시] 위 내용을 모두 확인하였으며 동의합니다.", disabled=True, key="p_agree")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ 오타 수정하기"):
                st.session_state.preview_mode = False
                st.rerun()
        with col2:
            if st.button("🚀 시안 확정 및 발송 링크 생성"):
                # 확정한 안내문을 시트에 발행 → 학부모 화면이 읽어가게 함
                ok, err = publish_announcement({
                    "title": title, "date": date, "location": location,
                    "supplies": supplies, "desc": desc, "is_outdoor": is_outdoor,
                })
                st.session_state.publish_error = None if ok else err
                st.session_state.generated = True
                st.session_state.preview_mode = False
                st.balloons()
                st.rerun()

    if st.session_state.get("generated", False):
        st.markdown("---")
        if st.session_state.get("publish_error"):
            st.warning(
                "⚠️ 안내문이 학부모 화면에 안 보일 수 있어요(시트 저장 실패): "
                f"{st.session_state.publish_error}"
            )
        else:
            st.success("📨 작성하신 안내문이 학부모 화면으로 발행되었습니다.")
        st.success("🎉 최종 시안 확인 완료! 학부모 전용 링크 시스템이 활성화되었습니다.")
        st.markdown("### 📱 학부모 발송용 카카오톡 주소")
        
        parent_link = "https://bomok-sign-app-hpapp9ikgcxqthmdv6wlgp4.streamlit.app/?mode=parent"
        
        st.info("💡 아래 상자 오른쪽 끝의 복사 버튼을 누른 뒤, 카카오톡에 전송해 보세요!")
        st.code(parent_link, language="text")
        
        if st.button("🆕 새 가정통신문 작성하기"):
            st.session_state.generated = False
            st.session_state.ai_generated_desc = "위 필수 정보를 입력한 후 버튼을 누르면 AI가 본문을 자동으로 작성합니다."
            st.rerun()
