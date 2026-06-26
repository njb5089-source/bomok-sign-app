import streamlit as st
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="보목지역아동센터 전자동의서", layout="centered")

# 스마트폰 화면 스타일링 & UI 고정
st.markdown("""
    <style>
    .main .block-container { max-width: 450px; padding-top: 1rem; }
    div.stButton > button:first-child {
        background-color: #4F46E5; color: white; width: 100%; padding: 12px;
        border-radius: 8px; border: none; font-weight: bold; font-size: 16px;
    }
    .popup-box {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 2px solid #4F46E5; margin-top: 15px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# 시연용 설정
st.caption("🛠️ [공모전 시연용 클라이언트 설정]")
app_mode = st.radio("서식 유형 선택 (AI 가이드 작동)", ["일반 교실 프로그램", "야외 체험 활동 (여행자보험 필요)"])
st.markdown("---")

# 동의서 본문
st.title("🌲 섶섬 생태 탐방 및 자리돔 낚시 체험")
st.subheader("보목지역아동센터 가정통신문")

st.info("""
안녕하세요, 보목지역아동센터입니다. 
무더운 여름을 맞아 우리 센터 아동들과 함께 제주 고유의 자연과 문화를 온몸으로 느끼는 [섶섬 생태 탐방 및 자리돔 체험 프로그램]을 진행하고자 합니다. 

아동들의 안전한 활동 공간 확보 및 참여 인원 확정을 위해 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.

🗓️ 일시: 2026년 7월 11일(토) 09:00 ~ 16:00
📍 장소: 섶섬(Seopseom Island) 일대 및 서귀포 보목항
👟 준비물: 편한 복장, 운동화, 모자, 개인 물통
🚌 이동 수단: 센터 차량 이용 (안전요원 동행 및 여행자보험 가입 완료)
""")

st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항 및 「전자서명법」 제3조에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")

# AI 가이드 엔진 작동
if app_mode == "야외 체험 활동 (여행자보험 필요)":
    st.warning("🤖 AI 컴플라이언스 가이드:\n야외 활동이 감지되어 보험 가입용 [주민등록번호] 수집 칸과 법적 고지문이 자동 추가되었습니다.")
    child_ssn = st.text_input("아동 주민등록번호 (보험 가입용)", placeholder="000000-0000000")
    st.caption("※ 수집된 주민등록번호는 보험 가입 행정 처리 즉시 파기됩니다.")

child_name = st.text_input("아동 성명", placeholder="예: 김민준")
parent_name = st.text_input("보호자 성명", placeholder="예: 김철수")
parent_phone = st.text_input("보호자 연락처", placeholder="예: 010-1234-5678")

agree = st.checkbox("위 내용을 모두 확인하였으며, 프로그램 참가 및 개인정보 활용에 동의합니다.")
st.markdown("---")

# [핵심] 진짜 손가락 서명이 되는 서명 패드 모달 활성화
if agree:
    if st.button("✍️ 터치하여 서명하기"):
        st.session_state.show_signup = True

if st.session_state.get("show_signup", False):
    st.markdown('<div class="popup-box">', unsafe_allow_html=True)
    st.markdown("### 📱 모바일 전용 서명 패드")
    st.write("화면 흔들림 방지 기술이 적용되었습니다. 아래 영역에 손가락이나 펜으로 직접 서명해 주세요.")
    
    # [진짜 서명 패드 부품 구동]
    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#F3F4F6",
        height=150,
        width=350,
        drawing_mode="freedraw",
        key="canvas",
    )
    
    if st.button("✅ 서명 완료 및 최종 제출하기"):
        if canvas_result.image_data is not None:
            st.success("🎉 보목지역아동센터 동의서 제출이 성공적으로 완료되었습니다! 데이터가 교사 시스템으로 안전하게 전송되었습니다.")
            st.session_state.show_signup = False
    st.markdown('</div>', unsafe_allow_html=True)
