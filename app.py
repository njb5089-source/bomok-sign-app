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
def generate_announcement_with_ai(title, date, location, supplies, extra_info,
                                  collected_items=None, purpose=None):
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

        # 수집할 개인정보 항목이 있으면, 본문에 '수집·이용 목적' 안내를 포함하도록 지시
        privacy_block = ""
        if collected_items:
            items_text = ", ".join(collected_items)
            purpose_text = (purpose or "").strip()
            if purpose_text:
                purpose_rule = (
                    "수집·이용 목적은 반드시 아래 담당자가 적은 내용을 그대로 사용하고, "
                    f"네가 임의로 추측하거나 지어내지 마:\n        \"{purpose_text}\""
                )
            else:
                purpose_rule = (
                    "수집·이용 목적이 입력되지 않았으니 절대 임의로 지어내지 말고, "
                    "'[수집·이용 목적: 담당 선생님이 별도 안내 예정]'이라고 그대로 표시할 것."
                )
            privacy_block = f"""
        [이번 동의서에서 수집할 개인정보 항목]
        {items_text}

        위 개인정보를 수집하므로, 본문 끝부분에 '개인정보 수집·이용 안내' 문단을 자연스럽게 포함해줘.
        - 수집 항목과 보유기간을 학부모가 이해하기 쉽게 안내할 것.
        - {purpose_rule}
        - 주민등록번호·건강정보 등 민감정보가 있으면 '관련 법령에 따라 안전하게 관리되며 목적 외 사용하지 않는다'는 안심 문구를 넣어줘.
        """

        prompt = f"""
        너는 보목지역아동센터의 따뜻하고 정중한 사회복지사야.
        아래 제공된 정보를 바탕으로 학부모님들께 모바일로 발송할 '가정통신문 안내문 본문'을 멋지게 작성해줘.

        [입력 정보]
        - 프로그램 제목: {title}
        - 일시: {date}
        - 장소: {location}
        - 준비물: {supplies}
        - 기타 강조사항: {extra_info}
        {privacy_block}
        그리고 본문에 반드시 '동의서의 항목에 동의하지 않으실 경우 프로그램 참여가 어려울 수 있습니다'라는 안내를 자연스럽게 포함해줘.
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


def mask_account(acc):
    """계좌번호 가운데를 가립니다. 예: 110****6789 (앞 3·뒤 4자리만 보관)"""
    digits = "".join(ch for ch in str(acc) if ch.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}{'*' * (len(digits) - 7)}{digits[-4:]}"
    return "(미입력 또는 형식 오류)"


def _open_spreadsheet():
    """구글 시트에 인증하고 스프레드시트를 엽니다."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(st.secrets["gcp_service_account_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(st.secrets["SHEET_ID"])


def save_to_gsheet(row):
    """제출 정보를 '제출현황' 탭에 한 줄 추가합니다. 설정 전이면 안전하게 실패합니다."""
    try:
        sh = _open_spreadsheet()
        try:
            sheet = sh.worksheet("제출현황")
        except gspread.WorksheetNotFound:
            sheet = sh.add_worksheet(title="제출현황", rows=300, cols=len(SUBMISSION_HEADER))
        existing = sheet.get_all_values()
        # 비어 있거나 머리글 구조가 다르면 1행에 머리글을 새로 깔아 줍니다.
        if not existing or existing[0] != SUBMISSION_HEADER:
            sheet.clear()
            sheet.append_row(SUBMISSION_HEADER)
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
        ws.append_row(["title", "date", "location", "supplies", "desc", "is_outdoor", "fields", "custom_fields"])
        ws.append_row([
            data["title"], data["date"], data["location"],
            data["supplies"], data["desc"], "Y" if data["is_outdoor"] else "N",
            data.get("fields", ""), data.get("custom_fields", ""),
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
            rec["field_ids"] = [x for x in str(rec.get("fields", "")).split(",") if x]
            try:
                cq = json.loads(rec.get("custom_fields", "") or "[]")
                rec["custom_questions"] = cq if isinstance(cq, list) else []
            except Exception:
                rec["custom_questions"] = []
            return rec
        return None
    except Exception:
        return None


# =====================================================================
# 📋 2-3. 수집 가능한 개인정보 항목 카탈로그
# =====================================================================
# always=True 항목은 어떤 동의서든 항상 수집합니다(아동·보호자 식별용).
# type: text(일반 입력), ssn(주민번호=마스킹 저장), consent(동의 체크)
PRIVACY_FIELDS = [
    {"id": "child_name",     "label": "아동 성명",                 "type": "text",    "ph": "예: 김민준",         "always": True},
    {"id": "guardian_name",  "label": "보호자 성명",               "type": "text",    "ph": "예: 김철수",         "always": True},
    {"id": "guardian_rel",   "label": "보호자와의 관계",           "type": "text",    "ph": "예: 부 / 모 / 조모",  "always": False},
    {"id": "guardian_phone", "label": "보호자 연락처",             "type": "text",    "ph": "예: 010-1234-5678",  "always": False},
    {"id": "emergency",      "label": "비상 연락처",               "type": "text",    "ph": "예: 010-...",        "always": False},
    {"id": "child_gender",   "label": "아동 성별",                 "type": "text",    "ph": "예: 남 / 여",         "always": False},
    {"id": "child_birth",    "label": "아동 생년월일",             "type": "text",    "ph": "예: 2015-03-01",     "always": False},
    {"id": "child_ssn",      "label": "아동 주민등록번호",         "type": "ssn",     "ph": "000000-0000000",     "always": False},
    {"id": "school",         "label": "소속 학교·학년",            "type": "text",    "ph": "예: ○○초 3학년",     "always": False},
    {"id": "address",        "label": "주소",                      "type": "text",    "ph": "예: 서귀포시 ...",   "always": False},
    {"id": "email",          "label": "이메일",                    "type": "text",    "ph": "예: abc@naver.com",  "always": False},
    {"id": "health",         "label": "건강·알레르기 특이사항",     "type": "text",    "ph": "예: 땅콩 알레르기",   "always": False},
    {"id": "medication",     "label": "복용 중인 약",              "type": "text",    "ph": "예: 천식 흡입제",     "always": False},
    {"id": "bank_account",   "label": "환불 계좌번호",             "type": "account", "ph": "예: 110-123-456789", "always": False},
    {"id": "emergency_med",  "label": "응급의료 처치 위임 동의",    "type": "consent", "ph": "",                   "always": False},
    {"id": "vehicle",        "label": "차량 탑승 동의",            "type": "consent", "ph": "",                   "always": False},
    {"id": "third_party",    "label": "개인정보 제3자(보험사 등) 제공 동의", "type": "consent", "ph": "",          "always": False},
    {"id": "portrait",       "label": "초상권(사진·영상) 활용 동의", "type": "consent", "ph": "",                  "always": False},
]
FIELDS_BY_ID = {f["id"]: f for f in PRIVACY_FIELDS}
LABEL_TO_ID = {f["label"]: f["id"] for f in PRIVACY_FIELDS}
ALWAYS_IDS = [f["id"] for f in PRIVACY_FIELDS if f["always"]]
OPTIONAL_FIELDS = [f for f in PRIVACY_FIELDS if not f["always"]]
# 민감정보로 분류되어 수집 시 경고가 필요한 항목들
SENSITIVE_IDS = {"child_ssn", "bank_account", "health", "medication"}

# 항목별로 자주 쓰는 '수집·이용 목적' 보기 (드롭다운). 마지막에 '기타' 자동 추가됨
PURPOSE_OPTIONS = {
    "guardian_rel":   ["본인 및 법정대리인 확인"],
    "guardian_phone": ["비상시 연락", "활동 안내·공지 전달"],
    "emergency":      ["응급상황 시 연락"],
    "child_gender":   ["활동 그룹 편성", "안전관리"],
    "child_birth":    ["보험 가입", "연령 확인 및 안전관리"],
    "child_ssn":      ["여행자보험 가입", "단체 상해보험 가입"],
    "school":         ["활동 그룹 편성", "출결·인솔 관리"],
    "address":        ["차량 운행(픽업) 경로 안내", "우편물 발송"],
    "email":          ["활동 결과·안내문 발송"],
    "health":         ["활동 중 안전관리·응급대응", "급식·간식 알레르기 관리"],
    "medication":     ["활동 중 건강관리·응급대응"],
    "bank_account":   ["참가비 환불"],
    "emergency_med":  ["응급상황 시 의료처치 위임"],
    "vehicle":        ["센터 차량 이동(픽업)"],
    "third_party":    ["보험 가입을 위한 보험사 제공", "활동 운영을 위한 체험기관 제공"],
    "portrait":       ["활동 사진·영상의 홍보·기록 활용", "센터 SNS·소식지 게시"],
}

# 제출현황 시트의 고정 머리글: 모든 항목을 각각의 열로 둠(안 받은 항목은 빈칸)
SUBMISSION_HEADER = (
    ["제출시각", "안내문 제목"]
    + [f["label"] for f in PRIVACY_FIELDS]
    + ["기타 입력 항목", "동의 여부", "서명"]
)


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
        field_ids = announcement.get("field_ids") or ALWAYS_IDS
    else:
        st.title("🌲 보목지역아동센터 가정통신문")
        st.caption("보목지역아동센터 가정통신문")
        st.warning("아직 선생님이 확정·발송한 안내문이 없습니다. 잠시 후 다시 확인해 주세요.")
        field_ids = ALWAYS_IDS + ["guardian_phone"]

    st.markdown("---")
    st.subheader("📝 동의서 작성 및 제출")

    # 교사가 선택한 항목만 입력란을 자동으로 만들어 줍니다.
    collected = {}          # 라벨 -> 시트에 저장할 값
    consent_items = []      # 동의형 항목은 개별 체크 대신 맨 아래 일괄 동의로 처리
    for fid in field_ids:
        f = FIELDS_BY_ID.get(fid)
        if not f:
            continue
        if f["type"] == "consent":
            consent_items.append(f["label"])
        elif f["type"] == "ssn":
            raw = st.text_input(f["label"], placeholder=f["ph"], key=f"pf_{fid}")
            collected[f["label"]] = mask_ssn(raw)       # 주민번호는 마스킹해서만 저장
        elif f["type"] == "account":
            raw = st.text_input(f["label"], placeholder=f["ph"], key=f"pf_{fid}")
            collected[f["label"]] = mask_account(raw)   # 계좌번호도 마스킹해서만 저장
        else:
            raw = st.text_input(f["label"], placeholder=f.get("ph", ""), key=f"pf_{fid}")
            collected[f["label"]] = raw

    # 교사가 구글 폼처럼 구성한 직접 추가 질문들
    custom_questions = announcement.get("custom_questions", []) if announcement else []
    custom_collected = {}
    for i, q in enumerate(custom_questions):
        lbl = q.get("label", "")
        if not lbl:
            continue
        qtype = q.get("type", "직접 기입")
        if qtype == "체크박스":
            checked = st.checkbox(lbl, key=f"pf_custom_{i}")
            custom_collected[lbl] = "예" if checked else "아니오"
        elif qtype == "객관식":
            opts = [o.strip() for o in str(q.get("options", "")).split(",") if o.strip()]
            if opts:
                custom_collected[lbl] = st.radio(lbl, opts, key=f"pf_custom_{i}")
            else:
                custom_collected[lbl] = st.text_input(lbl, key=f"pf_custom_{i}")
        else:
            custom_collected[lbl] = st.text_input(lbl, key=f"pf_custom_{i}")

    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    if consent_items:
        st.markdown("**동의가 필요한 항목**")
        for item in consent_items:
            st.markdown(f"- {item}")
    # 고정 안내 문구 (항상 표시)
    st.warning("⚠️ 위 항목에 동의하지 않으실 경우, 프로그램 참여가 어려울 수 있습니다.")
    agree = st.checkbox("위 내용을 모두 확인하였으며, 위 모든 항목에 동의합니다.")
    # 일괄 동의 결과를 각 동의형 항목에 반영
    for item in consent_items:
        collected[item] = "동의" if agree else "미동의"
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
            child_name_val = st.session_state.get("pf_child_name", "")
            guardian_name_val = st.session_state.get("pf_guardian_name", "")
            if not child_name_val or not guardian_name_val:
                st.error("⚠️ 아동 성명과 보호자 성명을 꼭 입력해 주세요.")
            elif not has_sign:
                st.error("⚠️ 서명란에 직접 서명을 해주세요.")
            else:
                # 머리글 순서에 맞춰 각 항목을 해당 열에 채워 넣습니다.
                custom_str = " | ".join(f"{lbl}: {val}" for lbl, val in custom_collected.items() if val)
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    announcement["title"] if announcement else "(안내문 없음)",
                ]
                row += [collected.get(f["label"], "") for f in PRIVACY_FIELDS]
                row += [custom_str, "동의함", "서명 완료"]
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
    
    is_outdoor = any(keyword in location for keyword in ["섬", "항", "바다", "산", "야외", "캠프", "공원", "체험"])

    st.markdown("---")
    st.write("### 🧩 2. 받을 개인정보 항목 선택")
    st.caption("받을 정보를 눌러 선택하세요. 선택한 항목은 진하게 표시됩니다. (아동 성명·보호자 성명은 항상 포함)")
    if "field_labels" not in st.session_state:
        st.session_state.field_labels = ["보호자 연락처"]   # 기본 추천
    if is_outdoor and "아동 주민등록번호" not in st.session_state.field_labels:
        st.info("🤖 야외 활동으로 감지됐어요. 보험 가입이 필요하면 '아동 주민등록번호'를 추가하세요.")
    selected_labels = st.pills(
        "받을 정보 선택",
        options=[f["label"] for f in OPTIONAL_FIELDS],
        selection_mode="multi",
        key="field_labels",
        disabled=is_disabled,
    ) or []
    selected_ids = ALWAYS_IDS + [LABEL_TO_ID[lbl] for lbl in selected_labels]

    # 직접 추가 질문 빌더 — 구글 폼처럼 질문을 1개씩 추가하고 형식을 고릅니다.
    st.markdown("**➕ 직접 추가 질문** (목록에 없는 항목을 구글 폼처럼 직접 구성)")
    if "custom_questions" not in st.session_state:
        st.session_state.custom_questions = []
    if "next_qid" not in st.session_state:
        st.session_state.next_qid = 1
    if not is_disabled and st.button("➕ 질문 추가"):
        # st.rerun()을 호출하지 않습니다. 호출하면 기존 질문 위젯이 그려지기 전에
        # 새로고침되어 객관식 보기 등 입력값이 사라집니다. 같은 실행 안에서 바로 렌더됩니다.
        st.session_state.custom_questions.append({"id": st.session_state.next_qid})
        st.session_state.next_qid += 1

    QTYPES = ["직접 기입", "체크박스", "객관식"]
    remove_id = None
    for q in st.session_state.custom_questions:
        qid = q["id"]
        c1, c2, c3 = st.columns([5, 3, 1])
        c1.text_input("질문", key=f"cq_label_{qid}", disabled=is_disabled, placeholder="예: 수영 가능 여부")
        qtype = c2.selectbox("형식", QTYPES, key=f"cq_type_{qid}", disabled=is_disabled)
        if not is_disabled and c3.button("🗑", key=f"cq_del_{qid}"):
            remove_id = qid
        if qtype == "객관식":
            st.text_input("　└ 선택지 (쉼표로 구분)", key=f"cq_opts_{qid}", disabled=is_disabled,
                          placeholder="예: 가능, 불가능, 보호자 동행 시 가능")
    if remove_id is not None:
        st.session_state.custom_questions = [
            qq for qq in st.session_state.custom_questions if qq["id"] != remove_id
        ]
        st.rerun()

    # 작성된 질문(라벨이 있는 것만)을 정의로 모읍니다.
    custom_questions_defs = []
    for q in st.session_state.custom_questions:
        qid = q["id"]
        lbl = st.session_state.get(f"cq_label_{qid}", "").strip()
        if not lbl:
            continue
        custom_questions_defs.append({
            "label": lbl,
            "type": st.session_state.get(f"cq_type_{qid}", "직접 기입"),
            "options": st.session_state.get(f"cq_opts_{qid}", ""),
        })
    custom_labels = [q["label"] for q in custom_questions_defs]

    # 상황별 자동 경고/권고
    is_water = any(k in location for k in ["바다", "해변", "해수욕", "물놀이", "수영", "계곡", "갯벌", "항", "섬"])
    is_overnight = any(k in location for k in ["1박", "2박", "캠프", "캠핑", "숙박", "야영", "수련"])
    if is_water:
        st.warning("🌊 수상·물놀이 활동으로 보입니다 → '응급의료 처치 위임 동의'와 안전 항목(예: 수영 가능 여부)을 권장합니다.")
    if is_overnight:
        st.warning("🏕️ 숙박 활동으로 보입니다 → '복용 중인 약', '비상 연락처', '응급의료 처치 위임 동의'를 권장합니다.")
    if "child_ssn" in selected_ids and "third_party" not in selected_ids:
        st.warning("📑 주민등록번호는 보통 보험사 등에 제공됩니다 → '개인정보 제3자 제공 동의'도 함께 받으세요.")
    sensitive_picked = [FIELDS_BY_ID[i]["label"] for i in selected_ids if i in SENSITIVE_IDS]
    if sensitive_picked:
        st.warning(
            "🔒 민감정보(" + ", ".join(sensitive_picked) + ") 수집 → 본문에 수집 목적을 명시해야 합니다. "
            "(아래 '수집·이용 목적'에 직접 적어주세요. 정식 버전에서는 암호화 보관 필요)"
        )

    # 항목마다 '수집·이용 목적'을 하나씩 지정 → AI가 추측하지 않고 이 내용을 그대로 사용
    purpose_parts = []
    if selected_labels or custom_labels:
        st.markdown("**📌 각 항목의 수집·이용 목적** (자주 쓰는 목적은 선택, 특수하면 '기타' 직접 입력)")
        for lbl in selected_labels:
            fid = LABEL_TO_ID[lbl]
            opts = PURPOSE_OPTIONS.get(fid, []) + ["기타(직접 입력)"]
            choice = st.selectbox(f"· {lbl}", opts, key=f"purpose_{fid}", disabled=is_disabled)
            if choice == "기타(직접 입력)":
                etc = st.text_input(f"　└ {lbl} 목적 직접 입력", key=f"purpose_etc_{fid}", disabled=is_disabled)
                val = etc.strip()
            else:
                val = choice
            if val:
                purpose_parts.append(f"{lbl}: {val}")
        for i, lbl in enumerate(custom_labels):
            etc = st.text_input(f"· {lbl} 목적 직접 입력", key=f"purpose_custom_{i}", disabled=is_disabled)
            if etc.strip():
                purpose_parts.append(f"{lbl}: {etc.strip()}")
    purpose = " / ".join(purpose_parts)

    st.markdown("---")
    st.write("### 🤖 3. AI 안내문 본문 생성")
    st.caption("위에서 고른 개인정보 항목의 '수집·이용 목적'까지 AI가 본문에 자동으로 포함합니다.")

    if not st.session_state.preview_mode:
        if st.button("🪄 AI 안내문 초안 자동 생성하기"):
            with st.spinner("Gemini AI가 멋진 가정통신문을 작성하고 있습니다..."):
                collected_items = [FIELDS_BY_ID[i]["label"] for i in selected_ids] + custom_labels
                generated_text = generate_announcement_with_ai(
                    title, date, location, supplies, extra_info, collected_items, purpose
                )
                st.session_state.ai_generated_desc = generated_text
                st.rerun()

    desc = st.text_area("상세 안내 문구", value=st.session_state.ai_generated_desc, height=250, disabled=is_disabled)
    # 입력칸에 직접 쓴 내용도 메모리에 저장 → 미리보기/수정 오가도 글이 사라지지 않음
    st.session_state.ai_generated_desc = desc

    if not st.session_state.preview_mode:
        st.markdown("---")
        if st.button("🔍 학부모용 서식 시안 미리보기"):
            st.session_state.preview_mode = True
            st.rerun()

    if st.session_state.preview_mode:
        st.markdown("---")
        st.markdown("### 📱 4. 학부모용 최종 발송 시안 확인")
        st.markdown('<div class="preview-container">', unsafe_allow_html=True)
        st.markdown(f"### 🌲 {title}")
        st.caption("보목지역아동센터 가정통신문")
        st.info(desc)
        st.markdown("##### 📋 학부모가 입력하게 될 항목")
        # 교사가 선택한 항목 그대로 미리보기에 표시 (동의형은 일괄 동의로 모음)
        pv_consent_items = []
        for fid in selected_ids:
            f = FIELDS_BY_ID.get(fid)
            if not f:
                continue
            if f["type"] == "consent":
                pv_consent_items.append(f["label"])
            else:
                tag = ""
                if f["type"] == "ssn":
                    tag = " (마스킹 저장)"
                elif f["type"] == "account":
                    tag = " (마스킹 저장)"
                st.text_input(f"[학부모 화면 예시] {f['label']}{tag}",
                              placeholder=f.get("ph", ""), disabled=True, key=f"pv_{fid}")
        for i, q in enumerate(custom_questions_defs):
            lbl = q["label"]
            if q["type"] == "체크박스":
                st.checkbox(f"[학부모 화면 예시] {lbl}", disabled=True, key=f"pv_custom_{i}")
            elif q["type"] == "객관식":
                opts = [o.strip() for o in str(q.get("options", "")).split(",") if o.strip()] or ["(선택지 미입력)"]
                st.radio(f"[학부모 화면 예시] {lbl}", opts, disabled=True, key=f"pv_custom_{i}")
            else:
                st.text_input(f"[학부모 화면 예시] {lbl} (직접 추가)", disabled=True, key=f"pv_custom_{i}")
        st.markdown("##### ⚖️ 법적 고지 및 개인정보 수집 동의")
        st.caption("본 동의서의 전자서명은 친필 서명과 동일한 법적 효력을 가집니다.")
        if pv_consent_items:
            st.markdown("**동의가 필요한 항목**")
            for item in pv_consent_items:
                st.markdown(f"- {item}")
        st.warning("⚠️ 위 항목에 동의하지 않으실 경우, 프로그램 참여가 어려울 수 있습니다.")
        st.checkbox("[학부모 화면 예시] 위 내용을 모두 확인하였으며, 위 모든 항목에 동의합니다.", disabled=True, key="p_agree")
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
                    "fields": ",".join(selected_ids),
                    "custom_fields": json.dumps(custom_questions_defs, ensure_ascii=False),
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
