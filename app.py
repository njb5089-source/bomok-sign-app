import streamlit as st
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="보목지역아동센터 시스템", layout="centered")

# CSS 스타일
st.markdown("""
    <style>
    .url-box { background-color: #E0E7FF; padding: 15px; border-radius: 8px; border: 2px solid #4F46E5; font-weight: bold; color: #3730A3; }
    </style>
""", unsafe_allow_html=True)

query_params = st.query_params
mode = query_params.get("mode")

# [학부모 모드]
if mode == "parent":
    st.title("🌲 섶섬 생태 탐방 동의서")
    child_ssn = st.text_input("아동 주민등록번호", placeholder="000000-0000000")
    child_name = st.text_input("아동 성명")
    parent_name = st.text_input("보호자 성명")
    parent_phone = st.text_input("보호자 연락처")
    
    if st.checkbox("동의합니다."):
        if st.button("✍️ 터치하여 서명하기"):
            st.session_state.show_signup = True
            
    if st.session_state.get("show_signup", False):
        canvas_result = st_canvas(fill_color="rgba(255, 255, 255, 0)", stroke_width=3, stroke_color="#000000", background_color="#F3F4F6", height=150, width=350, drawing_mode="freedraw", key="canvas_parent")
        if st.button("✅ 제출 완료"):
            st.success("제출되었습니다!")
            st.session_state.show_signup = False

# [교사 모드]
else:
    st.title("🛡️ 보목지역아동센터 관리자")
    
    # 교사용 입력 화면
    title = st.text_input("동의서 제목", "섶섬 생태 탐방 및 자리돔 낚시 체험")
    date = st.text_input("일시", "2026-07-11")
    loc = st.text_input("장소", "섶섬")
    
    if st.button("🚀 시안 확정 및 발송 링크 생성"):
        st.session_state.generated = True
        st.rerun()

    if st.session_state.get("generated", False):
        final_link = "https://bomok-sign-app.streamlit.app/?mode=parent"
        st.success("🎉 링크가 생성되었습니다!")
        st.markdown(f"### 📱 클릭해서 확인하세요")
        st.markdown(f"[{final_link}]({final_link})")
        st.markdown(f'<div class="url-box">{final_link}</div>', unsafe_allow_html=True)
        
        if st.button("🆕 새 통신문 작성"):
            st.session_state.generated = False
            st.rerun()
