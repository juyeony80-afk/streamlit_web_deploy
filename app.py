import datetime
import io
import json
from collections import defaultdict

import requests
import streamlit as st
import streamlit.components.v1 as components
from gtts import gTTS

st.title("연습용 미니 앱 - 약 스캔")

# ---------------------------------------------------------
# 서버 주소 설정 (백엔드 준비 전에는 로컬 mock 서버로 테스트)
# ---------------------------------------------------------
with st.sidebar:
    st.subheader("⚙️ 서버 설정")
    server_choice = st.radio(
        "연결할 서버",
        ["🧪 로컬 mock 서버 (테스트용)", "🌐 실제 백엔드 서버"],
        index=0,
    )
    if server_choice == "🧪 로컬 mock 서버 (테스트용)":
        BASE_URL = "http://127.0.0.1:5000"
        st.caption("mock_server.py를 먼저 터미널에서 실행해두세요.")
    else:
        BASE_URL = "https://medicinemisuseprevention.onrender.com"
    st.caption(f"현재 연결 주소: `{BASE_URL}`")

    st.divider()
    st.subheader("📋 메뉴")
    menu = st.radio(
        "화면 선택",
        ["💊 약 스캔/검색", "📅 복약 기록", "⏰ 알람 설정", "👪 보호자 연결"],
        label_visibility="collapsed",
    )

    st.divider()
    is_logged_in = st.checkbox(
        "🔐 로그인 상태 (데모용 토글)",
        value=st.session_state.get("is_logged_in", False),
        help="실제 로그인 기능이 아직 없어서, 서버 전송 로직을 테스트하기 위한 임시 스위치예요.",
    )
    st.session_state["is_logged_in"] = is_logged_in

# ---------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------
DEFAULTS = {
    "selected_id": None,
    "scan_result": None,
    "search_results": None,
    "view_mode": "📷 스캔으로 찾기",
    "audio_cache": {},
    "pin_verified": False,
    "elder_code": None,
    "guardian_linked_code": None,
    "guardian_permissions": {},
    "medication_records": [],
    "alarms": [],
}
for key, default_value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# ===========================================================
# 공용 함수
# ===========================================================
def speak_with_browser_tts(text: str):
    """
    Web Speech API(브라우저 내장 음성 합성)로 텍스트를 읽어줌.
    gTTS 생성이 실패했을 때 사용하는 대체 수단.
    """
    safe_text = json.dumps(text)
    html_code = f"""
    <div style="font-family:sans-serif;">
        <button id="tts-btn" style="
            background-color:#4a90d9; color:white; border:none; border-radius:8px;
            padding:10px 18px; font-size:1rem; cursor:pointer;
        ">🔊 음성으로 듣기</button>
        <button id="tts-stop-btn" style="
            background-color:#e0e0e0; color:#333; border:none; border-radius:8px;
            padding:10px 14px; font-size:1rem; margin-left:8px; cursor:pointer;
        ">⏹️ 정지</button>
        <div id="tts-status" style="margin-top:10px; font-size:0.95em; color:#4a90d9;"></div>
    </div>
    <script>
        const text = {safe_text};
        const playBtn = document.getElementById('tts-btn');
        const stopBtn = document.getElementById('tts-stop-btn');
        const status = document.getElementById('tts-status');
        function speak() {{
            if (!('speechSynthesis' in window)) {{
                status.innerText = '⚠️ 이 브라우저는 음성 재생을 지원하지 않아요.';
                return;
            }}
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = 'ko-KR';
            utter.rate = 0.9;
            status.innerText = '🔊 읽어드리는 중입니다...';
            utter.onend = function() {{ status.innerText = '✅ 다 읽었어요.'; }};
            utter.onerror = function() {{ status.innerText = '⚠️ 음성 재생 중 문제가 생겼어요.'; }};
            window.speechSynthesis.speak(utter);
        }}
        playBtn.addEventListener('click', speak);
        stopBtn.addEventListener('click', function() {{
            window.speechSynthesis.cancel();
            status.innerText = '⏹️ 멈췄어요.';
        }});
    </script>
    """
    components.html(html_code, height=110)


def format_error(error_data) -> str:
    """백엔드마다 error 필드 형태가 다를 수 있어 방어적으로 처리 (dict / str / None)."""
    if isinstance(error_data, dict):
        code = error_data.get("code")
        message = error_data.get("message")
        if code:
            return f"[{code}] {message}"
        return message or "알 수 없는 오류가 발생했어요."
    if isinstance(error_data, str) and error_data:
        return error_data
    return "알 수 없는 오류가 발생했어요."


# 데모용 고정 인증번호. 실서비스에서는 어르신이 직접 설정했거나 서버에서 검증하는 값으로 교체 필요.
DEMO_PIN = "0000"


def require_pin_verification() -> bool:
    """
    본인인증 화면: 고정 인증번호 입력 UI.
    맞으면 True를 반환하고, 세션 동안 다시 묻지 않음.
    """
    if st.session_state.get("pin_verified"):
        return True

    st.subheader("🔒 본인 확인")
    st.write("계속하려면 인증번호 4자리를 입력해주세요.")
    pin_input = st.text_input(
        "인증번호",
        type="password",
        max_chars=4,
        key="pin_input_field",
        label_visibility="collapsed",
        placeholder="****",
    )
    if st.button("확인", type="primary", key="pin_confirm_btn"):
        if pin_input == DEMO_PIN:
            st.session_state["pin_verified"] = True
            st.rerun()
        else:
            st.error("인증번호가 올바르지 않아요. 다시 입력해주세요.")
    return False


# ===========================================================
# 메뉴 1) 약 스캔/검색 (기존 기능)
# ===========================================================
if menu == "💊 약 스캔/검색":

    view_mode = st.radio(
        "찾는 방법 선택",
        ["📷 스캔으로 찾기", "🔍 이름으로 검색하기"],
        horizontal=True,
        key="view_mode",
    )

    st.divider()

    # ---- 스캔으로 찾기 ----
    if view_mode == "📷 스캔으로 찾기":

        input_method = st.radio("입력 방식 선택", ["📷 카메라로 촬영", "📁 파일 업로드"], horizontal=True)

        if input_method == "📷 카메라로 촬영":
            uploaded = st.camera_input("사진을 찍어보세요", key="camera_widget")
        else:
            uploaded = st.file_uploader("파일 선택", type=["jpg", "png"])

        if uploaded is not None:
            file_signature = (uploaded.name, uploaded.size)

            if st.session_state.get("last_file_signature") != file_signature:
                st.session_state["last_file_signature"] = file_signature
                st.session_state["scan_result"] = None
                st.session_state["selected_id"] = None
                st.info("새 파일이 선택됐어요. '스캔 시작하기'를 눌러주세요.")

            scan_clicked = st.button("🔍 스캔 시작하기", type="primary")

            if scan_clicked:
                st.session_state["selected_id"] = None
                st.session_state["scan_result"] = None

                with st.spinner("사진을 분석하고 있어요. 잠시만 기다려주세요..."):
                    try:
                        files = {"image": (uploaded.name, uploaded.getvalue())}
                        resp = requests.post(f"{BASE_URL}/medicines/scan", files=files, timeout=10)
                    except requests.exceptions.ConnectionError:
                        st.error("서버에 연결할 수 없어요. 서버 주소나 네트워크 연결을 확인해주세요.")
                        st.stop()
                    except requests.exceptions.Timeout:
                        st.error("서버 응답이 너무 오래 걸려요. 잠시 후 다시 시도해주세요.")
                        st.stop()
                    except requests.exceptions.RequestException as e:
                        st.error(f"요청 중 오류가 발생했어요: {e}")
                        st.stop()

                    try:
                        body = resp.json()
                    except ValueError:
                        st.error(f"서버 응답을 해석할 수 없어요. (상태 코드: {resp.status_code})")
                        st.stop()

                if resp.ok and body.get("success"):
                    st.session_state["scan_result"] = body["data"]
                else:
                    error_data = body.get("error")
                    st.error(format_error(error_data))
                    st.session_state["scan_result"] = None

        result = st.session_state.get("scan_result")
        if result:
            status = result.get("matchStatus")

            if status == "not_found":
                st.error("약을 인식하지 못했어요. 사진을 다시 찍어주시거나, 더 밝은 곳에서 촬영해보세요.")
                st.write("아니면 이름으로 직접 검색해볼 수도 있어요.")
                if st.button("🔍 이름으로 검색하러 가기"):
                    st.session_state["view_mode"] = "🔍 이름으로 검색하기"
                    st.rerun()

            elif status == "matched":
                st.session_state["selected_id"] = result["medicine"]["id"]

            elif status == "multiple_candidates":
                candidates = result.get("candidates", [])
                st.warning(f"비슷한 약이 {len(candidates)}개 있어요. 선택해주세요.")
                for item in candidates:
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**{item.get('name')}**")
                            st.caption(item.get("category"))
                        with col2:
                            if st.button("선택", key=f"pick_{item.get('id')}"):
                                st.session_state["selected_id"] = item.get("id")
            else:
                st.write("알 수 없는 응답 상태:", status)

    # ---- 이름으로 검색하기 ----
    else:
        st.write("약 이름을 알고 있다면 바로 검색해보세요.")

        with st.form("search_form"):
            query = st.text_input("약 이름 입력", placeholder="예: 타이레놀정")
            search_clicked = st.form_submit_button("🔍 검색하기", type="primary")

        if search_clicked and query.strip():
            st.session_state["selected_id"] = None
            st.session_state["search_results"] = None

            with st.spinner("검색하는 중..."):
                try:
                    resp = requests.get(
                        f"{BASE_URL}/medicines/search",
                        params={"query": query.strip()},
                        timeout=10,
                    )
                except requests.exceptions.ConnectionError:
                    st.error("서버에 연결할 수 없어요. 서버 주소나 네트워크 연결을 확인해주세요.")
                    st.stop()
                except requests.exceptions.Timeout:
                    st.error("서버 응답이 너무 오래 걸려요. 잠시 후 다시 시도해주세요.")
                    st.stop()
                except requests.exceptions.RequestException as e:
                    st.error(f"요청 중 오류가 발생했어요: {e}")
                    st.stop()

                try:
                    body = resp.json()
                except ValueError:
                    st.error(f"서버 응답을 해석할 수 없어요. (상태 코드: {resp.status_code})")
                    st.stop()

            if resp.ok and body.get("success"):
                data = body.get("data")
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("results") or data.get("candidates") or []
                else:
                    items = []
                st.session_state["search_results"] = items
            else:
                error_data = body.get("error")
                st.error(format_error(error_data))
                st.session_state["search_results"] = None

        results = st.session_state.get("search_results")
        if results is not None:
            if len(results) == 0:
                st.info("검색 결과가 없어요. 다른 이름으로 다시 검색해보세요.")
            else:
                st.write(f"검색 결과 {len(results)}건")
                for item in results:
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**{item.get('name')}**")
                            st.caption(item.get("category"))
                        with col2:
                            if st.button("선택", key=f"search_pick_{item.get('id')}"):
                                st.session_state["selected_id"] = item.get("id")

    # ---- 상세 정보 (스캔/검색 공통) ----
    if st.session_state.get("selected_id"):
        medicine_id = st.session_state["selected_id"]
        st.divider()
        with st.spinner("상세 정보 불러오는 중..."):
            try:
                detail_resp = requests.get(f"{BASE_URL}/medicines/{medicine_id}", timeout=10)
            except requests.exceptions.RequestException as e:
                st.error(f"상세 정보 요청 중 오류가 발생했어요: {e}")
                st.stop()

            try:
                detail_body = detail_resp.json()
            except ValueError:
                st.error(f"상세 정보 응답을 해석할 수 없어요. (상태 코드: {detail_resp.status_code})")
                st.stop()

        if detail_resp.ok and detail_body.get("success"):
            detail = detail_body["data"]
            raw_info = detail.get("rawInfo", {})

            with st.container(border=True):
                st.subheader(detail.get("name"))
                st.caption(detail.get("category"))

                easy_explanation = detail.get("easyExplanation")
                if easy_explanation:
                    st.markdown(
                        f"""
                        <div style="
                            background-color:#eef6ff; border-left:5px solid #4a90d9;
                            border-radius:8px; padding:14px 16px; margin:10px 0 16px 0;
                        ">
                            <div style="font-weight:600; margin-bottom:6px; color:#14385c;">
                                💊 이렇게 이해하면 쉬워요
                            </div>
                            <div style="font-size:1.05em; line-height:1.5; color:#1a1a1a;">
                                {easy_explanation}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                interactions = raw_info.get("interactions", [])
                if interactions:
                    interaction_html = "".join(f"<li>{item}</li>" for item in interactions)
                    st.markdown(
                        f"""
                        <div style="
                            background-color:#fff4e5; border-left:5px solid #e0902a;
                            border-radius:8px; padding:14px 16px; margin:0 0 16px 0;
                        ">
                            <div style="font-weight:600; margin-bottom:6px; color:#8a5a00;">
                                ⚠️ 함께 복용 시 주의하세요
                            </div>
                            <ul style="margin:0; padding-left:20px; font-size:1em; line-height:1.5; color:#1a1a1a;">
                                {interaction_html}
                            </ul>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.caption("ℹ️ 이 설명은 참고용이며, 정확한 복약 안내는 의사·약사와 상담해주세요.")

                with st.expander("자세한 정보 보기"):
                    st.write(f"복용법: {raw_info.get('usage')}")
                    st.write(f"효능: {raw_info.get('effect')}")
                    st.write(f"주의사항: {raw_info.get('precautions')}")
                    st.write(f"이럴 땐 병원: {', '.join(raw_info.get('emergencySigns', []))}")
                    st.write(f"함께 복용 주의: {', '.join(raw_info.get('interactions', []))}")

                st.write("")
                if st.button("🔊 음성으로 듣기"):
                    audio_cache = st.session_state["audio_cache"]
                    speak_text = f"{detail.get('name')}. {easy_explanation or ''}"

                    if medicine_id in audio_cache:
                        st.audio(audio_cache[medicine_id], format="audio/mp3")
                    else:
                        with st.spinner("음성을 만들고 있어요..."):
                            try:
                                buf = io.BytesIO()
                                gTTS(text=speak_text, lang="ko").write_to_fp(buf)
                                buf.seek(0)
                                audio_bytes = buf.read()
                                audio_cache[medicine_id] = audio_bytes
                            except Exception as e:
                                audio_bytes = None
                                st.warning(f"음성 생성에 실패했어요. 대신 브라우저 음성으로 읽어드릴게요. ({e})")

                        if audio_bytes:
                            st.audio(audio_bytes, format="audio/mp3")
                        else:
                            speak_with_browser_tts(speak_text)

                # 복약 기록 메뉴로 바로 이어지는 단축 버튼
                st.write("")
                if st.button("✅ 이 약, 오늘 복용했어요"):
                    today_str = datetime.date.today().isoformat()
                    record = {"date": today_str, "medicineName": detail.get("name")}
                    st.session_state["medication_records"].append(record)
                    if st.session_state.get("is_logged_in") and st.session_state.get("elder_code"):
                        try:
                            requests.post(
                                f"{BASE_URL}/medication/record",
                                json={"code": st.session_state["elder_code"], **record},
                                timeout=10,
                            )
                        except requests.exceptions.RequestException:
                            st.warning("서버 저장에는 실패했지만, 이 기기에는 기록됐어요.")
                    st.success(f"{today_str} - {detail.get('name')} 복용 기록 완료!")
        else:
            error_data = detail_body.get("error")
            st.error(format_error(error_data))


# ===========================================================
# 메뉴 2) 복약 기록
# ===========================================================
elif menu == "📅 복약 기록":
    st.subheader("오늘 약 드셨나요?")

    med_name_input = st.text_input("약 이름", placeholder="예: 타이레놀정", key="record_med_input")
    if st.button("✅ 오늘 약 복용했어요", type="primary"):
        if med_name_input.strip():
            today_str = datetime.date.today().isoformat()
            record = {"date": today_str, "medicineName": med_name_input.strip()}
            st.session_state["medication_records"].append(record)

            # 로그인 상태면 서버로도 전송, 아니면 세션(이 기기)에만 저장
            if st.session_state.get("is_logged_in"):
                if st.session_state.get("elder_code"):
                    try:
                        requests.post(
                            f"{BASE_URL}/medication/record",
                            json={"code": st.session_state["elder_code"], **record},
                            timeout=10,
                        )
                    except requests.exceptions.RequestException:
                        st.warning("서버 저장에는 실패했지만, 이 기기에는 기록됐어요.")
                else:
                    st.info("보호자 연결을 먼저 하면 서버에도 기록이 저장돼요. 지금은 이 기기에만 저장했어요.")
            st.success(f"{today_str} - {med_name_input} 복용 기록 완료!")
        else:
            st.warning("약 이름을 입력해주세요.")

    st.divider()
    st.write("**지금까지 기록**")
    records = st.session_state.get("medication_records", [])
    if not records:
        st.info("아직 기록이 없어요.")
    else:
        view_type = st.radio("보기 방식", ["리스트형", "달력형"], horizontal=True)
        if view_type == "리스트형":
            for r in sorted(records, key=lambda x: x["date"], reverse=True):
                st.write(f"- {r['date']} : {r['medicineName']}")
        else:
            by_date = defaultdict(list)
            for r in records:
                by_date[r["date"]].append(r["medicineName"])
            for date_str in sorted(by_date.keys(), reverse=True):
                meds = ", ".join(by_date[date_str])
                with st.container(border=True):
                    st.markdown(f"**{date_str}**")
                    st.write(f"✔️ {meds}")

    if not st.session_state.get("is_logged_in"):
        st.caption("ℹ️ 지금은 비로그인 상태라 이 기기(브라우저 세션)에만 저장돼요. 로그인하면 서버에도 저장돼요.")


# ===========================================================
# 메뉴 3) 알람 설정
# ===========================================================
elif menu == "⏰ 알람 설정":
    st.subheader("알람 설정")
    st.caption("※ 이 알람은 페이지가 열려 있는 브라우저 탭에서만 동작해요. 탭을 닫으면 알람도 사라져요.")

    col1, col2 = st.columns(2)
    with col1:
        alarm_time = st.time_input("알람 시간")
    with col2:
        alarm_med = st.text_input("약 이름", key="alarm_med_input", placeholder="예: 타이레놀정")

    if st.button("⏰ 알람 추가", type="primary"):
        if alarm_med.strip():
            st.session_state["alarms"].append(
                {"time": alarm_time.strftime("%H:%M"), "medicineName": alarm_med.strip()}
            )
            st.success("알람이 추가됐어요.")
        else:
            st.warning("약 이름을 입력해주세요.")

    if st.session_state["alarms"]:
        st.write("**등록된 알람**")
        for i, a in enumerate(st.session_state["alarms"]):
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"⏰ {a['time']} - {a['medicineName']}")
                with col2:
                    if st.button("삭제", key=f"del_alarm_{i}"):
                        st.session_state["alarms"].pop(i)
                        st.rerun()

    st.divider()
    st.write("**🔔 페이지 내 알림 테스트 (데모용)**")
    st.caption("페이지가 열려 있는 탭 안에서 큰 배너와 소리로 알려드려요.")
    test_seconds = st.number_input("몇 초 뒤 알림?", min_value=1, max_value=3600, value=5, step=1)
    test_message = st.text_input("알림 메시지", value="약 먹을 시간이에요!", key="alarm_test_msg")

    if st.button("🔔 테스트 알람 시작", type="primary"):
        safe_message = json.dumps(test_message)
        components.html(
            f"""
            <div id="alarm-status" style="font-family:sans-serif; color:#4a90d9; padding:6px 0;">
                ⏳ {test_seconds}초 후 알림이 울려요...
            </div>
            <script>
            (function() {{
                const status = document.getElementById('alarm-status');
                setTimeout(function() {{
                    status.innerHTML = `
                        <div style="
                            background-color:#ffe8e8;
                            border:2px solid #e05252;
                            border-radius:10px;
                            padding:18px;
                            font-size:1.3em;
                            font-weight:700;
                            color:#a11414;
                            text-align:center;
                        ">
                            🔔 {safe_message}
                        </div>
                    `;
                    try {{
                        const ctx = new (window.AudioContext || window.webkitAudioContext)();
                        function beep(delay) {{
                            const osc = ctx.createOscillator();
                            const gain = ctx.createGain();
                            osc.connect(gain);
                            gain.connect(ctx.destination);
                            osc.frequency.value = 880;
                            gain.gain.setValueAtTime(0.001, ctx.currentTime + delay);
                            gain.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + delay + 0.02);
                            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.25);
                            osc.start(ctx.currentTime + delay);
                            osc.stop(ctx.currentTime + delay + 0.3);
                        }}
                        beep(0);
                        beep(0.35);
                        beep(0.7);
                    }} catch (e) {{
                        console.log('beep failed', e);
                    }}
                }}, {test_seconds} * 1000);
            }})();
            </script>
            """,
            height=120,
        )


# ===========================================================
# 메뉴 4) 보호자 연결
# ===========================================================
elif menu == "👪 보호자 연결":
    role = st.radio("역할 선택", ["어르신 화면", "보호자 화면"], horizontal=True)
    st.divider()

    # ---- 어르신 화면 ----
    if role == "어르신 화면":
        if not require_pin_verification():
            st.stop()

        st.subheader("보호자 연결하기")

        if st.session_state.get("elder_code") is None:
            if st.button("🔗 보호자 연결하기", type="primary"):
                with st.spinner("코드를 발급받고 있어요..."):
                    try:
                        resp = requests.post(f"{BASE_URL}/guardian/code", timeout=10)
                        body = resp.json()
                    except requests.exceptions.RequestException as e:
                        st.error(f"코드 발급 중 오류가 발생했어요: {e}")
                        body = None

                if body and resp.ok and body.get("success"):
                    st.session_state["elder_code"] = body["data"]["code"]
                    st.rerun()
                elif body:
                    st.error(format_error(body.get("error")))
        else:
            code = st.session_state["elder_code"]
            st.markdown(
                f"""
                <div style="text-align:center; padding:30px; background-color:#eef6ff; border-radius:12px;">
                    <div style="font-size:1.1em; margin-bottom:10px; color:#14385c;">
                        이 번호를 보호자에게 알려주세요
                    </div>
                    <div style="font-size:2.8em; font-weight:700; letter-spacing:10px; color:#14385c;">
                        {code}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("보호자가 이 번호를 입력하고 권한을 선택하면 연동이 완료돼요.")

    # ---- 보호자 화면 ----
    else:
        st.subheader("보호자 코드 입력")
        guardian_code_input = st.text_input("6자리 코드 입력", max_chars=6, key="guardian_code_field")

        st.write("연동 후 받을 권한을 선택해주세요.")
        perm_records = st.checkbox("복약 기록 보기")
        perm_alerts = st.checkbox("알림 수신")
        perm_emergency = st.checkbox("비상연락")

        if st.button("연동하기", type="primary"):
            code_clean = guardian_code_input.strip()
            if not code_clean:
                st.warning("코드를 입력해주세요.")
            else:
                payload = {
                    "code": code_clean,
                    "permissions": {
                        "records": perm_records,
                        "alerts": perm_alerts,
                        "emergency": perm_emergency,
                    },
                }
                try:
                    resp = requests.post(f"{BASE_URL}/guardian/verify", json=payload, timeout=10)
                    body = resp.json()
                except requests.exceptions.RequestException as e:
                    st.error(f"연동 중 오류가 발생했어요: {e}")
                    body = None

                if body and resp.ok and body.get("success"):
                    st.session_state["guardian_linked_code"] = code_clean
                    st.session_state["guardian_permissions"] = payload["permissions"]
                    st.success("연동이 완료됐어요!")
                elif body:
                    st.error(format_error(body.get("error")))

        if st.session_state.get("guardian_linked_code"):
            st.divider()
            st.subheader("📋 연결된 어르신의 복약 기록")
            linked_code = st.session_state["guardian_linked_code"]
            permissions = st.session_state.get("guardian_permissions", {})

            if not permissions.get("records"):
                st.info("복약 기록 보기 권한이 선택되지 않았어요.")
            else:
                try:
                    resp = requests.get(f"{BASE_URL}/guardian/{linked_code}/records", timeout=10)
                    body = resp.json()
                except requests.exceptions.RequestException as e:
                    st.error(f"기록 조회 중 오류가 발생했어요: {e}")
                    body = None

                if body and resp.ok and body.get("success"):
                    records = body["data"].get("records", [])
                    if not records:
                        st.info("아직 기록된 복약 내역이 없어요.")
                    else:
                        for r in sorted(records, key=lambda x: x.get("date", ""), reverse=True):
                            st.write(f"- {r.get('date')} : {r.get('medicineName')} 복용 완료")
                elif body:
                    st.warning(format_error(body.get("error")))