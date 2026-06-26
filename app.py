import streamlit as st
from streamlit_drawable_canvas import st_canvas
import uuid

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

# 가상의 데이터베이스 및 상태 관리 변수 초기화
if "db" not in st.session_state:
    st.session_state.db = {}
if "preview_mode" not in st.session_state:
    st.session_state.preview_mode = False

# 주소창 파라미터 확인 (학부모 접속 여부 체크)
query_params = st.query_params
doc_id = query_params.get("id")

# =====================================================================
# [CASE 1] 학부모 전용 링크 접속 화면 (사인 제출 전용)
# =====================================================================
if doc_id and doc_id in st.session_state.db:
    data = st.session_state.db[doc_id]
    
    st.title(f"🌲 {data['title']}")
    st.subheader("보목지역아동센터 가정통신문")
    
    st.info(f"""
    안녕하세요, 보목지역아동센터입니다. 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.
    
    🗓️ 일시: {data['date']}
    📍 장소: {data['location']}
    👟 상세안내: {data['desc']}
    """)
    
    st.markdown("### ⚖️ 법적 고지 및 개인정보 수집 동의")
    st.caption("본 동의서의 전자서명은 「전자문서 및 전자거래 기본법」 제4조 제1항에 의거하여 친필 서명과 동일한 법적 효력을 가집니다.")
    
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
            st.success("🎉 보목지역아동센터 동의서 제출이 완료되었습니다!")
            st.session_state.show_signup = False
        st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# [CASE 2] 교사 포털 (관리자 화면)
# =====================================================================
else:
    st.title("🛡️ 보목지역아동센터 교사 포털")
    st.subheader("가정통신문 작성 및 AI 검증 시스템")
    st.markdown("---")
    
    # 1단계: 정보 입력 (시안 확인 모드일 때는 입력창을 잠금)
    st.write("### 📝 1. 동의서 내용 입력")
    is_disabled = st.session_state.preview_mode
    
    title = st.text_input("동의서 제목", "섶섬 생태 탐방 및 자리돔 낚시 체험", disabled=is_disabled)
    date = st.text_input("일시", "2026년 7월 11일(토) 09:00 ~ 16:00", disabled=is_disabled)
    location = st.text_input("장소 (야외 단어 입력 시 AI 엔진 작동)", "섶섬 일대 및 서귀포 보목항", disabled=is_disabled)
    desc = st.text_area("상세 안내 문구", "센터 차량을 이용하며 안전요원이 동행합니다.", disabled=is_disabled)
    
    # AI 엔진 실시간 야외 활동 판정 로직
    is_outdoor = any(keyword in location for keyword in ["섬", "항", "바다", "산", "야외", "캠프", "공원", "체험"])
    
    # 최초 작성 중일 때 미리보기 버튼 노출
    if not st.session_state.preview_mode:
        st.markdown("---")
        if st.button("🔍 학부모용 서식 시안 미리보기"):
            st.session_state.preview_mode = True
            st.rerun()

    # 2단계: 학부모용 서식 미리보기 시안 화면
    if st.session_state.preview_mode:
        st.markdown("---")
        st.markdown("### 📱 2. 학부모용 최종 발송 시안 확인")
        st.caption("초록색 박스 내부가 학부모 스마트폰에 그대로 띄워질 실물 화면입니다.")
        
        st.markdown('<div class="preview-container">', unsafe_allow_html=True)
        st.markdown(f"### 🌲 {title}")
        st.caption("보목지역아동센터 가정통신문")
        
        st.info(f"""
        안녕하세요, 보목지역아동센터입니다. 아래 내용을 확인하신 후, 동의 여부를 선택하여 서명 제출해 주시기 바랍니다.
        
        🗓️ 일시: {date}
        📍 장소: {location}
        👟 상세안내: {desc}
        """)
        
        st.markdown("##### ⚖️ 법적 고지 및 개인정보 수집 동의")
        st.caption("본 동의서의 전자서명은 친필 서명과 동일한 법적 효력을 가집니다.")
        
        if is_outdoor:
            st.warning("🤖 AI 컴플라이언스 엔진 감지:\n야외 활동 서식으로 판정되어 보험 가입용 [주민등록번호] 입력란 및 즉시 파기 고지문이 기본 탑재됩니다.")
            st.text_input("[학부모 화면 예시] 아동 주민등록번호 입력창", "000000-0000000", disabled=True)
            
        st.text_input("[학부모 화면 예시] 아동 성명", placeholder="아동 성명 입력란", disabled=True)
        st.text_input("[학부모 화면 예시] 보호자 성명", placeholder="보호자 성명 입력란", disabled=True)
        st.checkbox("[학부모 화면 예시] 위 내용을 모두 확인하였으며 동의합니다.", disabled=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        st.write("### ⚙️ 시안 최종 컨펌 및 수정")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ 오타 수정하기 (입력창 잠금 해제)"):
                st.session_state.preview_mode = False
                st.rerun()
                
        with col2:
            if st.button("🚀 시안 확정 및 발송 링크 생성"):
                new_id = str(uuid.uuid4())[:8]
                st.session_state.db[new_id] = {
                    "title": title, "date": date, "location": location, "desc": desc, "is_outdoor": is_outdoor
                }
                st.session_state.generated_id = new_id
                st.session_state.preview_mode = False
                st.balloons()
                st.rerun()

    # 최종 링크 생성 완료 화면
    if "generated_id" in st.session_state:
        st.markdown("---")
        st.success("🎉 최종 시안 확인 완료! 학부모 전용 모바일 전자동의서 주소가 빌드되었습니다.")
        
        parent_url = f"https://bomok-sign-app.streamlit.app/?id={st.session_state.generated_id}"
        
        st.markdown("### 📱 학부모 발송용 최종 카카오톡 주소")
        st.markdown(f'<div class="url-box">{parent_url}</div>', unsafe_allow_html=True)
        st.caption("위 주소를 복사해서 학부모님들께 카톡으로 전송하시면 됩니다.")
        
        if st.button("🆕 새 가정통신문 작성하기"):
            del st.session_state.generated_id
            st.rerun()
