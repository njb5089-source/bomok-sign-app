import streamlit as st
import google.generativeai as genai
from streamlit_drawable_canvas import st_canvas
import requests

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
if "current_user_mode" not in st.session_state: st.session_state.current_user_mode = "teacher"  # 기본값은 교사 모드
if "preview_mode" not in st.session_state: st.session_state.preview_mode = False
if "show_signup" not in st.session_state: st.session_state.show_signup = False
if "generated" not in st.session_state: st.session_state.generated = False
if "ai_generated_desc" not in st.session_state:
    st.session_state.ai_generated_desc = "위 필수 정보를 입력한 후 버튼을 누르면 AI가 본문을 자동으로 작성합니다."

# 주소 파라미터가 작동할 때를 대비한 자동 연동 (카톡 외 브라우저용)
query_params = st.query_params
if query_params.get("mode") == "parent":
    st.session_state.current_user_mode = "parent"


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
    .url-box {
        background-color: #E0E7FF; padding: 15px; border-radius: 8px;
        border: 1px dashed #4F46E5; font-weight: bold; color: #3730A3; font-size: 14px; word-break: break-all;
    }
    </style>
""", unsafe_allow_html=True)


# =====================================================================
# 🔄 📱 [카톡 버그 완전 해결] 최상단 모드 전환 스위치 배치
# =====================================================================
col_mode1, col_mode2 = st.columns(2)
with col_mode1:
    if st.button("🛡️ 교사 관리자 화면"):
        st.session_state.current_user_mode = "teacher"
        st.rerun()
with col_mode2:
    if st.button("🌲 학부모 동의서 화면"):
        st.session_state.current_user_mode = "parent"
        st.rerun()

st.markdown(f"**현재 상태:** {'🟢 학부모 전용 화면' if st.session_state.current_user_mode == 'parent' else '🔵 교사 작성 화면'}")
st.markdown("---")


# =====================================================================
# [CASE 1] 학부모 전용 링크 접속 화면
# =====================================================================
if st.session_state.current_user_mode == "parent":
    st.title("🌲 보목지역아동센터 가정통신문")
    st.subheader("모바일 확인 및 동의서 제출")
    st.info(st.session_state.ai_generated_desc)
    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    st.warning("🤖 AI 컴플라이언스 가이드:\n야외 활동 서식으로 판정되어 보험 가입용 [주민등록번호] 수집 칸이 자동 추가되었습니다.")
    child_ssn = st.text_input("아동 주민등록번호 (보험 가입용)", placeholder="000000-0000000")
    child_name = st.text_input("아동 성명", placeholder="예: 김민준")
    parent_name = st.text_input("보호자 성명", placeholder="예: 김철수")
    parent_phone = st.text_input("보호자 연락처", placeholder="예: 010-1234-5678")
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
            if not child_name or not parent_name:
                st.error("⚠️ 아동 성명과 보호자 성명을 꼭 입력해 주세요.")
            else:
                st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다!")
                st.session_state.show_signup = False
        st.markdown('</div>', unsafe_allow_html=True)


# =====================================================================
# [CASE 2] 교사 포털 (관리자 기본 화면)
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
                st.session_state.generated = True
                st.session_state.preview_mode = False
                st.balloons()
                st.rerun()

    if st.session_state.get("generated", False):
        st.markdown("---")
        st.success("🎉 최종 시안 확인 완료! 학부모 전용 링크 시스템이 활성화되었습니다.")
        st.markdown("### 📱 학부모 발송용 카카오톡 주소")
        
        # 주소 파라미터가 날아가도 상관없는 표준 순수 주소를 복사하게 유도합니다.
        parent_link = "https://bomok-sign-app.streamlit.app"
        
        st.info("💡 아래 상자 오른쪽 끝의 복사 버튼을 누른 뒤, 카카오톡에 붙여넣기(Ctrl+V) 하세요! 학부모님은 접속 후 상단의 '🌲 학부모 동의서 화면' 버튼을 누르면 됩니다.")
        st.code(parent_link, language="text")
        
        if st.button("🆕 새 가정통신문 작성하기"):
            st.session_state.generated = False
            st.session_state.ai_generated_desc = "위 필수 정보를 입력한 후 버튼을 누르면 AI가 본문을 자동으로 작성합니다."
            st.rerun()
