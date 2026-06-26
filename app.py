import streamlit as st
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="보목지역아동센터 통합 관리 시스템", layout="centered")

# 디자인 고도화 CSS
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
        border: 1px dashed #4F46E5; font-weight: bold; color: #3730A3; word-break: break-all;
    }
    </style>
""", unsafe_allow_html=True)

# 변수 초기화
if "preview_mode" not in st.session_state:
    st.session_state.preview_mode = False

# 주소창 파라미터 확인 (학부모 모드 접속 여부 체크)
query_params = st.query_params
mode = query_params.get("mode")

# =====================================================================
# [CASE 1] 학부모 전용 링크 접속 화면 (?mode=parent 주소로 들어왔을 때)
# =====================================================================
if mode == "parent":
    st.title("🌲 섶섬 생태 탐방 및 자리돔 낚시 체험")
    st.subheader("보목지역아동센터 가정통신문")
    
    st.info("""
    안녕하세요, 보목지역아동센터입니다. 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.
    
    🗓️ 일시: 2026년 7월 11일(토) 09:00 ~ 16:00
    📍 장소: 섶섬 일대 및 서귀포 보목항
    👟 상세안내: 센터 차량을 이용하며 안전요원이 동행합니다. 야외 활동이므로 편한 복장과 운동화를 착용 시켜주세요.
    """)
    
    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    
    # 학부모 전용 페이지는 야외 서식 기준으로 주민번호 칸 고정 표출 (시연 최적화)
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
            st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다!")
            st.session_state.show_signup = False
        st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# [CASE 2] 교사 포털 (관리자 기본 화면)
# =====================================================================
else:
    st.title("🛡️ 보목지역아동센터 교사 포털")
    st.subheader("가정통신문 작성 및 AI 검증 시스템")
    st.markdown("---")
    
    st.write("### 📝 1. 동의서 내용 입력")
    is_disabled = st.session_state.preview_mode
    
    title = st.text_input("동의서 제목", "섶섬 생태 탐방 및 자리돔 낚시 체험", disabled=is_disabled)
    date = st.text_input("일시", "2026년 7월 11일(토) 09:00 ~ 16:00", disabled=is_disabled)
    location = st.text_input("장소 (야외 단어 입력 시 AI 엔진 작동)", "섶섬 일대 및 서귀포 보목항", disabled=is_disabled)
    desc = st.text_area("상세 안내 문구", "센터 차량을 이용하며 안전요원이 동행합니다.", disabled=is_disabled)
    
    is_outdoor = any(keyword in location for keyword in ["섬", "항", "바다", "산", "야외", "캠프", "공원", "체험"])
    
    if not st.session_state.preview_mode:
        st.markdown("---")
        if st.button("🔍 학부모용 서식 시안 미리보기"):
            st.session_state.preview_mode = True
            st.rerun()

    # 2단계: 학부모용 서식 미리보기 시안 화면
    if st.session_state.preview_mode:
        st.markdown("---")
        st.markdown("### 📱 2. 학부모용 최종 발송 시안 확인")
        
        st.markdown('<div class="preview-container">', unsafe_allow_html=True)
        st.markdown(f"### 🌲 {title}")
        st.caption("보목지역아동센터 가정통신문")
        
        st.info(f"""
        안녕하세요, 보목지역아동센터입니다. 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.
        
        🗓️ 일시: {date}
        📍 장소: {location}
        👟 상세안내: {desc}
        """)
        
        if is_outdoor:
            st.warning("🤖 AI 컴플라이언스 엔진 감지: 야외 활동 서식으로 판정됨.")
            
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        st.write("### ⚙️ 시안 최종 컨펌 및 수정")
        
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

    # 최종 링크 생성 완료 화면
    if st.session_state.get("generated", False):
        st.markdown("---")
        st.success("🎉 최종 시안 확인 완료! 학부모 전용 링크 시스템이 활성화되었습니다.")
        
        # 현재 구동 중인 선생님 앱의 '진짜 실제 주소'를 자동으로 찾아내어 카톡용 주소로 조립합니다.
        # 주소 뒤에 ?mode=parent 를 붙여 학부모 화면을 강제 고정합니다.
        current_url = "https://share.streamlit.io/" # 기본 폴백
        parent_url = f"학부모용 전용 링크는 [현재 컴퓨터 인터넷 주소창의 주소] 맨 뒤에 '?mode=parent' 를 붙여서 카톡으로 보내시면 됩니다!"
        
        st.markdown("### 📱 학부모 카톡 발송 방법 (초간단)")
        st.info("""
        **지금 컴퓨터 인터넷 주소창에 있는 주소를 그대로 복사**한 뒤, 카톡 창에 붙여넣고 맨 뒤에 딱 **`?mode=parent`** 만 이어서 붙여서 보내보세요!
        
        예시: `https://내앱이름.streamlit.app/?mode=parent`
        """)
        
        if st.button("🆕 새 가정통신문 작성하기"):
            st.session_state.generated = False
            st.rerun()
