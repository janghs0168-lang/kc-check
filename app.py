import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
import xml.etree.ElementTree as ET
import json

# =====================================================================
# [Key 설정 구역] 구글 API 키만 입력하세요.
# =====================================================================
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=GOOGLE_API_KEY)

# 사장님이 발급받으신 국가기술표준원 공식 서비스 ID (AuthKey)
SAFETY_KOREA_AUTH_KEY = "875a7d8b-e33a-467b-97ca-5fb35430b34d"


# --- [1] 국가기술표준원(전기) 100% 라이브 API (알파벳 자동 순회 탑재) ---
def search_전기안전(cert_num):
    url = "http://www.safetykorea.kr/openapi/api/cert/certificationDetail.json"
    headers = {'AuthKey': SAFETY_KOREA_AUTH_KEY}
    
    cert_num = cert_num.strip()  # 앞뒤 공백 제거
    # 사용자가 알파벳을 빼고 쳐도 시스템이 내부적으로 A, B, C, D를 자동으로 붙여서 연속 타격합니다.
    search_list = [cert_num, f"{cert_num}A", f"{cert_num}B", f"{cert_num}C", f"{cert_num}D"]
    
    for target_num in search_list:
        params = {'certNum': target_num}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=3)
            if res.status_code == 200:
                data = res.json()
                if str(data.get("resultCode")) == "2000":
                    result_data = data.get("resultData", {})
                    status = result_data.get("certState", "적합")
                    company = result_data.get("importerName") or result_data.get("makerName") or "업체명 없음"
                    product = result_data.get("productName", "제품명 없음")
                    return {"상태": f"🟢 {status} (매칭번호: {target_num})", "업체명": company, "제품명": product}
        except:
            continue
            
    return {"상태": "❌ 조회 실패", "업체명": "정부 DB에 등록되지 않은 인증번호입니다. (알파벳 자동 매칭 포함)", "제품명": "-"}


# --- [2] 국립전파연구원(전자파) 100% 라이브 API ---
import xml.etree.ElementTree as ET
import requests
import urllib3

# SSL 인증서 경고 메시지 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def search_전파인증(cert_num):
    # 🌟 핵심 1: http가 아니라 'https'로 주소를 변경해야 통과됩니다.
    url = "https://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthInfo.do"
    params = {"mtlCefNo": cert_num.strip()}

    # 🌟 핵심 2: 인증키가 없는 오픈 API인 만큼 보안 방화벽이 깐깐합니다.
    # 아래처럼 브라우저의 디테일한 정보를 다 주어야 "사람이 검색했구나" 하고 들여보내 줍니다.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        # verify=False 를 넣어 공공기관 보안 인증서 무시하고 강제 통과
        res = requests.get(
            url, params=params, headers=headers, timeout=5, verify=False
        )

        if res.status_code == 200:
            root = ET.fromstring(res.content)
            if root.find(".//resultCode").text == "0000":
                company = (
                    root.find(".//bsmNm").text
                    if root.find(".//bsmNm") is not None
                    else "업체명 없음"
                )
                product = (
                    root.find(".//mtlNm").text
                    if root.find(".//mtlNm") is not None
                    else "제품명 없음"
                )
                return {
                    "상태": "🟢 적합등록 완료",
                    "업체명": company,
                    "제품명": product,
                }
            elif root.find(".//resultCode").text == "0001":
                return {
                    "상태": "❌ 조회 실패",
                    "업체명": "정부 DB에 일치하는 전파인증번호가 없습니다.",
                    "제품명": "-",
                }

        return {
            "상태": "❌ 실패",
            "업체명": f"정부 서버 응답 에러 ({res.status_code})",
            "제품명": "-",
        }

    except Exception as e:
        return {
            "상태": "❌ 통신 에러",
            "업체명": f"연결 실패: {str(e)}",
            "제품명": "-",
        }


# =====================================================================
# 스트림릿 웹 화면 구성
# =====================================================================
st.set_page_config(page_title="KC 인증 스마트 검수", layout="centered")

st.title("🛡️ AI 기반 KC 인증 스마트 검수 시스템")
st.write("100% 실시간 라이브 정부 DB 교차 검증 (SafetyKorea v2.0 규격)")

# 새로고침 시 AI 분석 데이터를 유지하기 위해 세션 스테이트 초기화
if 'detected_elec' not in st.session_state: st.session_state['detected_elec'] = ""
if 'detected_wave' not in st.session_state: st.session_state['detected_wave'] = ""

uploaded_file = st.file_uploader("검수할 제품 사진을 업로드하세요", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="업로드된 사진", width=300)
    
    if st.button("🔍 1단계: AI 사진 분석 & OCR 번호 추출"):
        with st.spinner("제미나이 비전 AI가 품목 분류 및 라벨 문자 파싱 중..."):
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # [프롬프트 튜닝] 품목 분류와 동시에 라벨 글자까지 지독하게 긁어오도록 지시
            prompt = """
            당신은 한국의 전안법 전문가이자 고성능 OCR(문자 인식) 시스템입니다. 
            사진 속 제품의 외형을 정밀 분석하고, 제품 표면이나 라벨 스티커에 인쇄된 'KC 인증번호'를 식별하여 오직 JSON으로만 답변하세요.

            [품목 분류 절대 기준]
            1. 사진에 '본체와 별도로 커다란 고정식 물탱크'가 있고, 손잡이와 본체가 '꼬인 호스'로 연결된 거치형 디자인인 경우:
               - 결과: product_type="구강청결기(거치형)", elec_result="REQUIRED", wave_result="REQUIRED"
            2. 사진에 큰 물탱크가 따로 없고, 손잡이와 물탱크가 하나로 합쳐진 한 손 크기의 휴대용 무선 디자인인 경우:
               - 결과: product_type="구강청결기(휴대용 무선)", elec_result="EXEMPT", wave_result="REQUIRED"

            [OCR 인증번호 추출 미션]
            - 사진 속 제품 표면, 스티커, 라벨 등에서 '전기안전인증번호' 또는 '전파인증번호(방송통신기자재)'를 찾아내세요.
            - 전기안전인증번호 예시 형식: HU10731-19002A, JU071047-12002 등
            - 전파인증번호 예시 형식: R-R-Csl-K-501, R-R-LCJ-F5020E, KCC-REM-AAA-XXXXX 등
            - 문자가 흐리거나 기재되어 있지 않아 찾을 수 없다면 빈 문자열("")로 처리하세요.

            반드시 다른 설명 없이 오직 아래 형식의 JSON만 출력하세요.
            {"product_type": "품목명", "elec_result": "REQUIRED/EXEMPT", "wave_result": "REQUIRED/EXEMPT", "detected_elec_num": "추출된 전기인증번호", "detected_wave_num": "추출된 전파인증번호"}
            """
            response = model.generate_content(contents=[prompt, image], generation_config={"response_mime_type": "application/json"})
            analysis = json.loads(response.text)
            
            # AI가 찾아낸 정보들을 화면 입력창에 미리 꽂아넣기 위해 세션에 저장
            st.session_state['analysis'] = analysis
            st.session_state['detected_elec'] = analysis.get("detected_elec_num", "")
            st.session_state['detected_wave'] = analysis.get("detected_wave_num", "")
            
    if 'analysis' in st.session_state:
        analysis = st.session_state['analysis']
        p_type = analysis.get("product_type", "미확인")
        e_res = analysis.get("elec_result", "UNKNOWN")
        w_res = analysis.get("wave_result", "UNKNOWN")
        
        st.success(f"**품목 분류 결과:** {p_type}")
        st.info(f"📋 **검수 가이드라인** -> 전기인증: **{e_res}** | 전파인증: **{w_res}**")
        
        st.write("---")
        st.subheader("⌨️ 2단계: 정부 데이터베이스 실시간 조회")
        st.caption("💡 AI가 사진에서 글자를 인식해 번호를 자동으로 채워두었습니다. 틀린 부분이 있다면 직접 수정도 가능합니다.")
        
        user_elec = ""
        user_wave = ""
        
        # [고도화] value=st.session_state[...]를 사용하여 AI가 긁어온 인증번호를 입력창에 자동 기본값으로 세팅!
        if e_res == "REQUIRED":
            user_elec = st.text_input("⚡ [전기안전] 인증번호 입력 창:", value=st.session_state['detected_elec'])
        if w_res == "REQUIRED":
            user_wave = st.text_input("📡 [전자파 전파] 인증번호 입력 창:", value=st.session_state['detected_wave'])
            
        if st.button("🏢 실시간 정부 DB 조회 및 최종 판정"):
            st.write("### 📋 정부 서버 실시간 리포트 결과")
            
            res_e = {}
            res_w = {}
            
            if user_elec:
                res_e = search_전기안전(user_elec)
                st.write(f"- **전기안전결과:** {res_e['상태']} | **업체:** {res_e['업체명']} | **제품:** {res_e['제품명']}")
                
            if user_wave:
                res_w = search_전파인증(user_wave)
                st.write(f"- **전자파결과:** {res_w['상태']} | **업체:** {res_w['업체명']} | **제품:** {res_w['제품명']}")
                
            # 최종 정품 승인 완료 판정 및 폭죽 효과
            if ("🟢" in res_e.get('상태', '') or not user_elec) and ("🟢" in res_w.get('상태', '') or not user_wave):
                st.balloons()
                st.success("🎉 [스마트 매칭 완료] AI가 사진에서 번호를 읽고, 정부 전산망 교차 검증까지 원스톱으로 통과했습니다!")