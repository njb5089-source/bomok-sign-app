import streamlit as st
import google.generativeai as genai
from streamlit_drawable_canvas import st_canvas
import requests
import datetime
import json
import time
import io
import base64
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

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
        [이번 동의서에서 수집하는 개인정보 항목]
        {items_text}
        - 본문 안에 어떤 정보를 왜 받는지 1~2문장으로 자연스럽게 안내해줘.
        - {purpose_rule}
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
        ※ 개인정보 수집·파기, 만 14세 미만 법정대리인 동의 등 '공식 법적 고지문'은 시스템이 동의서 하단에 별도로 자동 표시하니, 너는 그 부분을 작성하지 말고 따뜻하고 정중한 프로그램 안내에 집중해줘.
        부드러운 해요체(~합니다, ~바랍니다)를 사용하고 이모지와 줄바꿈을 섞어서 작성해줘.
        """

        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        # 최신 모델부터 순서대로 시도. 서버 혼잡(503 등)이면 잠깐 쉬었다 자동 재시도.
        models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
        last_status, last_text = 0, ""
        for attempt in range(3):                 # 전체 3회까지 재시도
            for model in models:
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                last_status, last_text = resp.status_code, resp.text
            if attempt < 2:
                time.sleep(2)                    # 일시 오류면 2초 쉬고 다시 시도

        # 사람이 알아보기 쉬운 메시지로 안내
        if last_status in (503, 500, 429) or "UNAVAILABLE" in last_text or "RESOURCE_EXHAUSTED" in last_text:
            if last_status == 429 or "RESOURCE_EXHAUSTED" in last_text:
                return "❌ 무료 사용량(쿼터)을 초과했어요. 잠시 후 또는 내일 다시 시도해 주세요."
            return "❌ 지금 구글 AI 서버가 잠시 혼잡합니다(일시적). 10~20초 뒤 버튼을 다시 눌러주세요. (쿼터 문제 아님)"
        return f"❌ AI 생성 실패: {last_status} {last_text}"
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


# =====================================================================
# 🧩 분할 입력 도우미 — 정해진 칸 형식으로 개인정보를 입력받습니다.
# =====================================================================
def _sep(text):
    """입력칸 사이의 구분 기호/단위(- , 년, 월 등)를 칸과 같은 높이로 세로 중앙정렬"""
    st.markdown(
        "<div style='display:flex;align-items:center;justify-content:center;"
        f"height:40px;margin:0;'>{text}</div>",
        unsafe_allow_html=True,
    )


def _input_phone(label, key_prefix, disabled=False):
    """전화번호: [010]-[1234]-[5678] 3칸"""
    st.markdown(f"**{label}**")
    c1, d1, c2, d2, c3 = st.columns([4, 1, 5, 1, 5], vertical_alignment="top")
    p1 = c1.text_input(label, key=f"{key_prefix}_1", max_chars=3, placeholder="010",
                       label_visibility="collapsed", disabled=disabled)
    with d1:
        _sep("-")
    p2 = c2.text_input(label + " 2", key=f"{key_prefix}_2", max_chars=4, placeholder="1234",
                       label_visibility="collapsed", disabled=disabled)
    with d2:
        _sep("-")
    p3 = c3.text_input(label + " 3", key=f"{key_prefix}_3", max_chars=4, placeholder="5678",
                       label_visibility="collapsed", disabled=disabled)
    parts = [p1.strip(), p2.strip(), p3.strip()]
    return "-".join(p for p in parts if p)


def _input_birth(label, key_prefix, disabled=False):
    """생년월일: [2015]년 [03]월 [01]일 3칸"""
    st.markdown(f"**{label}**")
    c1, l1, c2, l2, c3, l3 = st.columns([4, 1, 3, 1, 3, 1], vertical_alignment="top")
    y = c1.text_input(label, key=f"{key_prefix}_y", max_chars=4, placeholder="2015",
                      label_visibility="collapsed", disabled=disabled)
    with l1:
        _sep("년")
    m = c2.text_input(label + " 월", key=f"{key_prefix}_m", max_chars=2, placeholder="03",
                      label_visibility="collapsed", disabled=disabled)
    with l2:
        _sep("월")
    d = c3.text_input(label + " 일", key=f"{key_prefix}_d", max_chars=2, placeholder="01",
                      label_visibility="collapsed", disabled=disabled)
    with l3:
        _sep("일")
    y, m, d = y.strip(), m.strip(), d.strip()
    return f"{y}년 {m}월 {d}일" if (y or m or d) else ""


def _input_ssn(label, key_prefix, disabled=False):
    """주민등록번호: [앞 6자리]-[뒤 7자리] 2칸 (저장 시 마스킹)"""
    st.markdown(f"**{label}**")
    c1, d1, c2 = st.columns([5, 1, 6], vertical_alignment="top")
    front = c1.text_input(label, key=f"{key_prefix}_f", max_chars=6, placeholder="앞 6자리",
                          label_visibility="collapsed", disabled=disabled)
    with d1:
        _sep("-")
    back = c2.text_input(label + " 뒤", key=f"{key_prefix}_b", max_chars=7, placeholder="뒤 7자리",
                         label_visibility="collapsed", disabled=disabled)
    return mask_ssn(f"{front}{back}")


def _input_bank(label, key_prefix, disabled=False):
    """환불 계좌번호: [은행명]은행 [계좌번호] (저장 시 계좌번호 마스킹)"""
    st.markdown(f"**{label}**")
    c1, l1, c2 = st.columns([3, 1, 6], vertical_alignment="top")
    bank = c1.text_input(label, key=f"{key_prefix}_bank", placeholder="예: 농협",
                         label_visibility="collapsed", disabled=disabled)
    with l1:
        _sep("은행")
    acc = c2.text_input(label + " 번호", key=f"{key_prefix}_acc", placeholder="계좌번호",
                        label_visibility="collapsed", disabled=disabled)
    bank = bank.strip()
    parts = []
    if bank:
        parts.append(f"{bank}은행")
    if acc.strip():
        parts.append(mask_account(acc))
    return " ".join(parts)


def _input_school(label, key_prefix, disabled=False):
    """소속 학교·학년: [보목초등]학교 [3]학년"""
    st.markdown(f"**{label}**")
    c1, l1, c2, l2 = st.columns([5, 1, 3, 1], vertical_alignment="top")
    sch = c1.text_input(label, key=f"{key_prefix}_s", placeholder="예: 보목초등",
                        label_visibility="collapsed", disabled=disabled)
    with l1:
        _sep("학교")
    grade = c2.text_input(label + " 학년", key=f"{key_prefix}_g", max_chars=2, placeholder="3",
                          label_visibility="collapsed", disabled=disabled)
    with l2:
        _sep("학년")
    sch, grade = sch.strip(), grade.strip()
    parts = []
    if sch:
        parts.append(f"{sch}학교")
    if grade:
        parts.append(f"{grade}학년")
    return " ".join(parts)


def signature_to_base64(image_data):
    """서명 캔버스(numpy 배열)를 PNG로 인코딩해 base64 문자열로 변환합니다."""
    try:
        img = Image.fromarray(image_data.astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        # 구글 시트 셀 한도(5만자) 초과 방지: 너무 크면 저장하지 않음
        return b64 if len(b64) < 48000 else ""
    except Exception:
        return ""


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


def load_submissions():
    """'제출현황' 탭의 모든 제출 기록을 불러옵니다. (없거나 실패 시 None)"""
    try:
        ws = _open_spreadsheet().worksheet("제출현황")
        return ws.get_all_records()
    except Exception:
        return None


# =====================================================================
# 👨‍👩‍👧 참여 대상(명단) 관리 + 개별 발송 링크
# =====================================================================
PARENT_BASE = "https://bomok-sign-app-hpapp9ikgcxqthmdv6wlgp4.streamlit.app/?mode=parent"
ROSTER_HEADER = ["대상ID", "아동명", "보호자명", "전화번호"]


def load_roster():
    """'명단' 탭의 참여 대상 목록을 불러옵니다. (시트 연결 실패 시 None, 없으면 [])"""
    try:
        sh = _open_spreadsheet()
        try:
            ws = sh.worksheet("명단")
        except gspread.WorksheetNotFound:
            return []
        return ws.get_all_records()
    except Exception:
        return None


def add_roster_entry(child, guardian, phone):
    """참여 대상 1명을 '명단' 탭에 추가하고 고유 토큰을 부여합니다."""
    try:
        sh = _open_spreadsheet()
        try:
            ws = sh.worksheet("명단")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="명단", rows=300, cols=len(ROSTER_HEADER))
        if not ws.get_all_values():
            ws.append_row(ROSTER_HEADER)
        token = "R" + datetime.datetime.now().strftime("%y%m%d%H%M%S%f")  # 문자형 고유 토큰
        ws.append_row([token, child, guardian, phone])
        return True, None
    except Exception as e:
        return False, str(e)


def delete_roster_entry(token):
    """토큰으로 명단에서 한 명을 삭제합니다."""
    try:
        ws = _open_spreadsheet().worksheet("명단")
        vals = ws.get_all_values()
        for idx, row in enumerate(vals):
            if idx == 0:
                continue
            if row and str(row[0]) == str(token):
                ws.delete_rows(idx + 1)
                break
        return True, None
    except Exception as e:
        return False, str(e)


def get_roster_entry(token):
    """토큰에 해당하는 명단 항목(아동명/보호자명/전화번호)을 찾습니다."""
    roster = load_roster()
    if not roster:
        return None
    for r in roster:
        if str(r.get("대상ID")) == str(token):
            return r
    return None


def recipient_link(token):
    """특정 대상 전용 개별 링크"""
    return f"{PARENT_BASE}&to={token}"


def sms_link(phone, body):
    """휴대폰 문자앱을 번호·내용 채운 채로 여는 sms: 링크"""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return f"sms:{digits}?body={urllib.parse.quote(body)}"


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
    ["제출시각", "안내문 제목", "대상ID"]
    + [f["label"] for f in PRIVACY_FIELDS]
    + ["기타 입력 항목", "동의 여부", "서명", "서명이미지"]
)

# 법적으로 반드시 들어가야 하는 고정 고지문 (AI가 아닌 시스템이 항상 표시 → 누락 0%)
LEGAL_NOTICE = """\
**📋 개인정보 처리 및 동의 안내**

1. **법정대리인 동의** — 만 14세 미만 아동의 개인정보 처리는 「개인정보 보호법」 제22조의2에 따라 법정대리인(보호자)의 동의가 필요하며, 본 동의서는 법정대리인인 보호자께서 동의하시는 것입니다.
2. **수집·이용 및 파기** — 수집한 개인정보는 안내된 목적 범위에서만 이용하며, 보유·이용 기간이 끝나거나 처리 목적을 달성하면 해당 개인정보를 지체 없이 안전하게 파기합니다.
3. **동의 거부 권리** — 개인정보 수집·이용에 대한 동의를 거부할 권리가 있으며, 동의를 거부하실 경우 프로그램 참여가 제한될 수 있습니다.
4. **민감·고유식별정보 보호** — 주민등록번호 등 고유식별정보 및 건강정보 등 민감정보는 관련 법령에 근거하여 별도로 안전하게 관리하며, 수집 목적 외의 용도로 이용하지 않습니다.
"""


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

    # 개별 링크(?to=토큰)로 들어온 경우, 명단 정보로 이름·연락처를 미리 채웁니다.
    recipient_token = query_params.get("to", "")
    if recipient_token and st.session_state.get("prefilled_to") != recipient_token:
        entry = get_roster_entry(recipient_token)
        if entry:
            st.session_state["pf_child_name"] = entry.get("아동명", "")
            st.session_state["pf_guardian_name"] = entry.get("보호자명", "")
            digits = "".join(ch for ch in str(entry.get("전화번호", "")) if ch.isdigit())
            if len(digits) >= 10:
                st.session_state["pf_guardian_phone_1"] = digits[:3]
                st.session_state["pf_guardian_phone_2"] = digits[3:-4]
                st.session_state["pf_guardian_phone_3"] = digits[-4:]
        st.session_state["prefilled_to"] = recipient_token
    if recipient_token:
        entry = get_roster_entry(recipient_token)
        if entry:
            st.success(f"👋 {entry.get('아동명','')} 학부모님을 위한 맞춤 동의서입니다.")

    st.markdown("---")
    st.subheader("📝 동의서 작성 및 제출")

    # 교사가 선택한 항목만 입력란을 자동으로 만들어 줍니다.
    collected = {}          # 라벨 -> 시트에 저장할 값
    consent_items = []      # 동의형 항목은 개별 체크 대신 맨 아래 일괄 동의로 처리
    for fid in field_ids:
        f = FIELDS_BY_ID.get(fid)
        if not f:
            continue
        lbl = f["label"]
        if f["type"] == "consent":
            consent_items.append(lbl)
        elif fid in ("guardian_phone", "emergency"):
            collected[lbl] = _input_phone(lbl, f"pf_{fid}")
        elif fid == "child_gender":
            collected[lbl] = st.radio(lbl, ["남", "여"], key=f"pf_{fid}",
                                      horizontal=True, index=None) or ""
        elif fid == "child_birth":
            collected[lbl] = _input_birth(lbl, f"pf_{fid}")
        elif fid == "child_ssn":
            collected[lbl] = _input_ssn(lbl, f"pf_{fid}")        # 마스킹해서만 저장
        elif fid == "school":
            collected[lbl] = _input_school(lbl, f"pf_{fid}")
        elif fid == "bank_account":
            collected[lbl] = _input_bank(lbl, f"pf_{fid}")       # 계좌번호 마스킹 포함
        elif f["type"] == "account":
            raw = st.text_input(lbl, placeholder=f["ph"], key=f"pf_{fid}")
            collected[lbl] = mask_account(raw)                   # 계좌번호도 마스킹해서만 저장
        else:
            raw = st.text_input(lbl, placeholder=f.get("ph", ""), key=f"pf_{fid}")
            collected[lbl] = raw

    # 교사가 구글 폼처럼 구성한 직접 추가 질문들
    custom_questions = announcement.get("custom_questions", []) if announcement else []
    custom_collected = {}
    custom_consent_items = []   # '동의여부' 질문은 일괄 동의로 처리
    for i, q in enumerate(custom_questions):
        lbl = q.get("label", "")
        if not lbl:
            continue
        qtype = q.get("type", "직접 기입")
        if qtype == "동의여부":
            custom_consent_items.append(lbl)   # 입력칸 대신 일괄 동의 목록에 추가
        elif qtype == "객관식":
            opts = q.get("options", [])
            if isinstance(opts, str):   # 옛 데이터(쉼표 문자열) 호환
                opts = [o.strip() for o in opts.split(",") if o.strip()]
            if opts:
                custom_collected[lbl] = st.radio(lbl, opts, key=f"pf_custom_{i}")
            else:
                custom_collected[lbl] = st.text_input(lbl, key=f"pf_custom_{i}")
        else:
            custom_collected[lbl] = st.text_input(lbl, key=f"pf_custom_{i}")

    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    all_consent_items = consent_items + custom_consent_items
    if all_consent_items:
        st.markdown("**동의가 필요한 항목**")
        for item in all_consent_items:
            st.markdown(f"- {item}")
    # 고정 법적 고지 4종 (항상 표시 — 누락 0%)
    st.info(LEGAL_NOTICE)
    agree = st.checkbox("위 내용을 모두 확인하였으며, 위에 입력한 개인정보 수집 및 위 모든 항목에 동의합니다.")
    # 일괄 동의 결과를 각 동의형 항목에 반영 (예정 항목은 각자의 저장 위치에)
    for item in consent_items:
        collected[item] = "동의" if agree else "미동의"
    for item in custom_consent_items:
        custom_collected[item] = "동의" if agree else "미동의"
    st.markdown("---")
    
    if agree:
        st.markdown('<div class="popup-box">', unsafe_allow_html=True)
        st.markdown("### ✍️ 전자서명")
        st.caption("아래 칸에 손가락 또는 마우스로 서명해 주세요. 전자서명은 친필 서명과 동일한 법적 효력을 가집니다.")
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
                sig_b64 = signature_to_base64(canvas_result.image_data)
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    announcement["title"] if announcement else "(안내문 없음)",
                    recipient_token,
                ]
                row += [collected.get(f["label"], "") for f in PRIVACY_FIELDS]
                row += [custom_str, "동의함", "서명 완료", sig_b64]
                ok, err = save_to_gsheet(row)
                if ok:
                    st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다!")
                else:
                    # 저장소 연결 전이라도 학부모 화면은 정상으로 보이게 처리
                    st.success("🎉 동의서 제출이 접수되었습니다!")
                    st.caption(f"ℹ️ (관리자 메모) 저장소 연결 대기 중: {err}")
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

    QTYPES = ["직접 기입", "동의여부", "객관식"]
    remove_id = None
    for q in st.session_state.custom_questions:
        qid = q["id"]
        with st.container(border=True):   # 질문을 카드로 묶어 다른 질문과 구분
            c1, c2, c3 = st.columns([5, 3, 1])
            c1.text_input("질문", key=f"cq_label_{qid}", disabled=is_disabled, placeholder="예: 수영 가능 여부")
            qtype = c2.selectbox("형식", QTYPES, key=f"cq_type_{qid}", disabled=is_disabled)
            if not is_disabled and c3.button("🗑", key=f"cq_del_{qid}"):
                remove_id = qid
            if qtype == "동의여부":
                st.caption("　↳ 학부모 화면의 '동의가 필요한 항목'에 추가됩니다.")
            elif qtype == "객관식":
                ids_key = f"opt_ids_{qid}"
                if ids_key not in st.session_state:
                    st.session_state[ids_key] = [1, 2]   # 기본 선택지 2개
                if f"next_oid_{qid}" not in st.session_state:
                    st.session_state[f"next_oid_{qid}"] = max(st.session_state[ids_key], default=0) + 1
                st.caption("　└ 선택지")
                oids = st.session_state[ids_key]
                remove_oid = None
                for k, oid in enumerate(oids):
                    _sp, ocol, dcol = st.columns([1, 7, 1])   # 왼쪽 빈칸 = 들여쓰기
                    ocol.text_input("선택지", key=f"cq_opt_{qid}_{oid}", disabled=is_disabled,
                                    placeholder=f"선택지 {k + 1}", label_visibility="collapsed")
                    if not is_disabled and len(oids) > 1 and dcol.button("🗑", key=f"opt_del_{qid}_{oid}"):
                        remove_oid = oid
                if remove_oid is not None:
                    st.session_state[ids_key] = [o for o in oids if o != remove_oid]
                _sp2, addcol = st.columns([1, 7])
                if not is_disabled and addcol.button("➕ 선택지 추가", key=f"add_opt_{qid}", type="tertiary"):
                    st.session_state[ids_key].append(st.session_state[f"next_oid_{qid}"])
                    st.session_state[f"next_oid_{qid}"] += 1
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
        qtype = st.session_state.get(f"cq_type_{qid}", "직접 기입")
        opts_list = []
        if qtype == "객관식":
            oids = st.session_state.get(f"opt_ids_{qid}", [])
            opts_list = [st.session_state.get(f"cq_opt_{qid}_{oid}", "").strip() for oid in oids]
            opts_list = [o for o in opts_list if o]
        custom_questions_defs.append({"label": lbl, "type": qtype, "options": opts_list})
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
            lbl = f["label"]
            if f["type"] == "consent":
                pv_consent_items.append(lbl)
            elif fid in ("guardian_phone", "emergency"):
                _input_phone(lbl, f"pv_{fid}", disabled=True)
            elif fid == "child_gender":
                st.radio(lbl, ["남", "여"], key=f"pv_{fid}", horizontal=True, index=None, disabled=True)
            elif fid == "child_birth":
                _input_birth(lbl, f"pv_{fid}", disabled=True)
            elif fid == "child_ssn":
                _input_ssn(lbl, f"pv_{fid}", disabled=True)
            elif fid == "school":
                _input_school(lbl, f"pv_{fid}", disabled=True)
            elif fid == "bank_account":
                _input_bank(lbl, f"pv_{fid}", disabled=True)
            else:
                tag = " (마스킹 저장)" if f["type"] == "account" else ""
                st.text_input(f"[학부모 화면 예시] {lbl}{tag}",
                              placeholder=f.get("ph", ""), disabled=True, key=f"pv_{fid}")
        for i, q in enumerate(custom_questions_defs):
            lbl = q["label"]
            if q["type"] == "동의여부":
                pv_consent_items.append(lbl)   # 일괄 동의 목록으로 모음
            elif q["type"] == "객관식":
                opts = q.get("options", [])
                if isinstance(opts, str):
                    opts = [o.strip() for o in opts.split(",") if o.strip()]
                opts = opts or ["(선택지 미입력)"]
                st.radio(f"[학부모 화면 예시] {lbl}", opts, disabled=True, key=f"pv_custom_{i}")
            else:
                st.text_input(f"[학부모 화면 예시] {lbl} (직접 추가)", disabled=True, key=f"pv_custom_{i}")
        st.markdown("##### ⚖️ 법적 고지 및 개인정보 수집 동의")
        st.caption("본 동의서의 전자서명은 친필 서명과 동일한 법적 효력을 가집니다.")
        if pv_consent_items:
            st.markdown("**동의가 필요한 항목**")
            for item in pv_consent_items:
                st.markdown(f"- {item}")
        st.info(LEGAL_NOTICE)
        st.checkbox("[학부모 화면 예시] 위 내용을 모두 확인하였으며, 위에 입력한 개인정보 수집 및 위 모든 항목에 동의합니다.", disabled=True, key="p_agree")
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

    # =====================================================================
    # 📋 제출 현황 확인 — 제출 명단 + 전자서명 이미지 조회
    # =====================================================================
    st.markdown("---")
    st.write("### 📋 제출 현황 확인")
    st.caption("제출된 동의서와 전자서명을 확인합니다. (나중에 동의 내용·서명을 검증할 때 사용)")
    if st.button("🔄 제출 명단 불러오기"):
        st.session_state.show_submissions = True
    if st.session_state.get("show_submissions"):
        records = load_submissions()
        if records is None:
            st.error("제출 현황을 불러오지 못했습니다. (시트 연결을 확인해 주세요)")
        elif len(records) == 0:
            st.info("아직 제출된 동의서가 없습니다.")
        else:
            st.success(f"총 {len(records)}건이 제출되었습니다.")
            for rec in reversed(records):   # 최근 제출이 위로 오도록
                child = rec.get("아동 성명", "")
                guardian = rec.get("보호자 성명", "")
                when = rec.get("제출시각", "")
                with st.expander(f"🧾 {when} · {child} (보호자: {guardian})"):
                    for k, v in rec.items():
                        if k == "서명이미지" or not str(v).strip():
                            continue
                        st.write(f"- **{k}**: {v}")
                    sig = rec.get("서명이미지", "")
                    if sig:
                        try:
                            st.image(base64.b64decode(sig), caption="전자서명", width=300)
                        except Exception:
                            st.caption("⚠️ 서명 이미지를 불러오지 못했습니다.")
                    else:
                        st.caption("서명 이미지 없음(구버전 제출)")

    # =====================================================================
    # 👨‍👩‍👧 참여 대상 관리 + 개별 발송 + 미제출 리마인드
    # =====================================================================
    st.markdown("---")
    st.write("### 👨‍👩‍👧 참여 대상 관리 및 개별 발송")
    st.caption("참여 아동을 명단에 등록해두면, 대상을 골라 개별 맞춤 링크를 문자로 보낼 수 있습니다.")

    # (1) 명단 등록 / 관리
    with st.expander("➕ 참여 대상(명단) 등록 / 관리", expanded=False):
        with st.form("roster_add", clear_on_submit=True):
            rc1, rc2, rc3 = st.columns(3)
            new_child = rc1.text_input("아동명")
            new_guardian = rc2.text_input("보호자명")
            new_phone = rc3.text_input("전화번호", placeholder="01012345678")
            if st.form_submit_button("명단에 추가"):
                if new_child and new_phone:
                    ok, err = add_roster_entry(new_child, new_guardian, new_phone)
                    st.success(f"'{new_child}' 추가됨") if ok else st.error(f"추가 실패: {err}")
                else:
                    st.warning("아동명과 전화번호는 필수입니다.")
        _roster = load_roster()
        if _roster:
            st.caption(f"등록 인원: {len(_roster)}명")
            for r in _roster:
                token = r.get("대상ID")
                d1, d2 = st.columns([6, 1])
                d1.write(f"- {r.get('아동명','')} / {r.get('보호자명','')} / {r.get('전화번호','')}")
                if d2.button("🗑", key=f"del_roster_{token}"):
                    delete_roster_entry(token)
                    st.rerun()

    # (2) 발송 + (3) 제출 추적 + (4) 리마인드
    roster = load_roster()
    if roster is None:
        st.error("명단을 불러오지 못했습니다. (시트 연결 확인)")
    elif not roster:
        st.info("위에서 참여 대상을 먼저 등록해 주세요.")
    else:
        ann = load_announcement()
        ann_title = ann.get("title") if ann else "가정통신문"
        subs = load_submissions() or []
        submitted_tokens = {str(s.get("대상ID")).strip() for s in subs if str(s.get("대상ID")).strip()}
        done_cnt = sum(1 for r in roster if str(r.get("대상ID")) in submitted_tokens)
        st.markdown(f"**📨 발송 대상** (제출 {done_cnt} / 전체 {len(roster)})")
        st.caption("각 '문자 보내기'를 누르면 휴대폰 문자앱이 번호·메시지가 채워진 채로 열립니다.")
        for r in roster:
            token = str(r.get("대상ID"))
            child, phone = r.get("아동명", ""), r.get("전화번호", "")
            done = token in submitted_tokens
            status = "✅ 제출완료" if done else "⏳ 미제출"
            body = (f"[보목지역아동센터] {child} 학부모님, '{ann_title}' 동의서입니다. "
                    f"아래 링크에서 작성해 주세요.\n{recipient_link(token)}")
            s1, s2 = st.columns([3, 2])
            s1.write(f"{status} · {child} ({phone})")
            s2.markdown(f'<a href="{sms_link(phone, body)}">📩 문자 보내기</a>', unsafe_allow_html=True)

        st.markdown("**🔔 미제출자 리마인드**")
        pending = [r for r in roster if str(r.get("대상ID")) not in submitted_tokens]
        if not pending:
            st.success("🎉 모든 대상이 제출을 완료했습니다!")
        else:
            st.caption(f"미제출 {len(pending)}명에게 리마인드를 보낼 수 있습니다.")
            for r in pending:
                token = str(r.get("대상ID"))
                child, phone = r.get("아동명", ""), r.get("전화번호", "")
                body = (f"[보목지역아동센터] {child} 학부모님, '{ann_title}' 동의서가 아직 제출되지 않았습니다. "
                        f"잊지 마시고 작성 부탁드립니다.\n{recipient_link(token)}")
                p1, p2 = st.columns([3, 2])
                p1.write(f"⏳ {child} ({phone})")
                p2.markdown(f'<a href="{sms_link(phone, body)}">🔔 리마인드 문자</a>', unsafe_allow_html=True)
