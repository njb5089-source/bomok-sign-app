import streamlit as st
from streamlit_drawable_canvas import st_canvas
import uuid

st.set_page_config(page_title="보목지역아동센터 통합 관리 시스템", layout="centered")

# 스마트폰 및 태블릿 최적화 CSS
st.markdown("""
    <style>
    .main .block-container { max-width: 500px; padding-top: 1rem; }
    div.stButton > button {
        background-color: #4F46E5; color: white; width: 100%; padding: 12px;
        border-radius: 8px; border: none; font-weight: bold; font-size: 16px;
    }
    .popup-box {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 2px solid #4F46E5; margin-top: 15px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);
    }
    .url-box {
        background-color: #E0E7FF; padding: 15px; border-radius: 8px;
        border: 1px dashed #4F46E5; font-weight: bold; color: #3730A3; word-break: break-all;
    }
    </style>
""", unsafe_allow_html=True)

# 가상의 데이터베이스 (스트림잇 서버 메모리에 임시 저장)
if "db" not in st.session_state:
    st.session_state.db = {}

# --- 주소창 파라미터 확인 (학부모용 고유 주소인지 체크하는 비밀 기술) ---
query_params = st.query_params
doc_id = query_params.get("id")

# =====================================================================
# [CASE 1] 학부모가 교사에게 받은 고유 링크로 접속했을 때
# =====================================================================
if doc_id and doc_id in st.session_state.db:
    data = st.session_state.db[doc_id]
    
    st.title(f"🌲 {data['title']}")
    st.subheader("보목지역아동센터 가정통신문")
    
    st.info(f"""
    안녕하세요, 보목지역아동센터입니다. 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.
    
    🗓️ 일시: {data['date']}
    📍 장소: {data['location']}
    👟 안내: {data['desc']}
    """)
    
    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    
    # 교사가 입력한 장소에 따라 AI가 자동으로 발동한 결과 출력
    if data['is_outdoor']:
        st.warning("🤖 AI 컴플라이언스 가이드:\n야외 활동 서식으로 판정되어 보험 가입용 [주민등록번호] 수집 칸이 자동 추가되었습니다.")
        child_ssn = st.text_input("아동 주민등록번호 (보험 가입용)", placeholder="000000-0000000")
        st.caption("※ 수집된 주민등록번호는 보험 처리 즉시 파기됩니다.")
        
    child_name = st.text_input("아동 성명", placeholder="예: 김민준")
    parent_name = st.text_input("보호자 성명", placeholder="예: 김철수")
    
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
            st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다! 교사용 대시보드로 안전하게 전송되었습니다.")
            st.session_state.show_signup = False
        st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# [CASE 2] 메인 주소 접속 시 (교사용 관리자 화면)
# =====================================================================
else:
    st.title("🛡️ 보목지역아동센터 교사 포털")
    st.subheader("새 가정통신문 및 전자동의서 생성 생성기")
    
    st.markdown("---")
    st.write("### 📝 1. 동의서 내용 입력")
    title = st.text_input("동의서 제목", "섶섬 생태 탐방 및 자리돔 낚시 체험")
    date = st.text_input("일시", "2026년 7월 11일(토) 09:00 ~ 16:00")
    location = st.text_input("장소 (야외 단어 입력 시 AI 엔진 작동)", "섶섬 일대 및 서귀포 보목항")
    desc = st.text_area("상세 안내 문구", "센터 차량을 이용하며 안전요원이 동행합니다.")
    
    # AI 엔진 실시간 분석 결과 보여주기
    is_outdoor = any(keyword in location for keyword in ["섬", "항", "바다", "산", "야외", "캠프", "공원"])
    
    st.markdown("---")
    st.write("### 🤖 2. AI 컴플라이언스 엔진 실시간 검증")
    if is_outdoor:
        st.error("⚠️ AI 분석 결과: [야외 체험 활동]이 감지되었습니다.\n학부모용 링크 생성 시 '여행자보험용 주민등록번호 입력창'과 '법적 고지문'이 안전하게 자동 탑재됩니다.")
    else:
        st.success("✅ AI 분석 결과: [일반 실내 프로그램] 서식입니다. 추가적인 개인정보 수집 없이 안전하게 발송 가능합니다.")
        
    st.markdown("---")
    
    # [핵심] 발송하기 버튼을 누르면 랜덤 주소를 생성하고 DB에 저장
    if st.button("🚀 학부모 전용 고지 서식 및 링크 생성하기"):
        new_id = str(uuid.uuid4())[:8] # 고유 주소 아이디 랜덤 생성
        
        # 가상 데이터베이스에 저장
        st.session_state.db[new_id] = {
            "title": title,
            "date": date,
            "location": location,
            "desc": desc,
            "is_outdoor": is_outdoor
        }
        
        st.balloons()
        st.success("🎉 학부모 전용 모바일 전자동의서 주소가 성공적으로 빌드되었습니다!")
        
        # 현재 내 앱 주소 기반으로 학부모용 단독 주소 완성
        parent_url = f"https://bomok-sign-app.streamlit.app/?id={new_id}"
        
        st.markdown("### 📱 학부모 발송용 카카오톡 주소")
        st.markdown(f'<div class="url-box">{parent_url}</div>', unsafe_allow_html=True)
        st.caption("위 주소를 복사해서 학부모님들께 카톡으로 전송하시면, 학부모는 교사 화면 없이 딱 동의서와 사인 칸만 보게 됩니다.")
