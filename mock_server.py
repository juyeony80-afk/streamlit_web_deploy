"""
로컬 테스트용 mock 백엔드 서버
실행: python mock_server.py
(처음 한 번만) pip install flask gTTS

프론트엔드 app.py의 BASE_URL을 http://127.0.0.1:5000 으로 맞추면 연결됩니다.

케이스 제어 방법 (파일명으로 구분):
  - 파일명이 "타이레놀정.jpg" 처럼 DB에 있는 상품명 전체와 정확히 같으면        → matched
  - 파일명이 "고혈압.jpg" 처럼 category와 같으면                              → multiple_candidates
  - 그 외 (예: "abcxyz.jpg")                                                → not_found

TTS: CLOVA Voice 대신 gTTS(무료) 사용. 같은 약은 최초 1회만 mp3를 생성하고
     그 다음부터는 audio_cache 폴더에 저장된 파일을 재사용함 (LLM 캐싱과 같은 취지 - 비용/시간 절감).
     ⚠️ gTTS는 구글 서버에 실시간으로 요청을 보내기 때문에 인터넷 연결이 필요합니다.
"""

import os
import random

from flask import Flask, request, jsonify, send_from_directory
from gtts import gTTS

app = Flask(__name__)

AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_cache")
os.makedirs(AUDIO_DIR, exist_ok=True)

# 보호자 연결 코드 저장소 (메모리 기반 - 서버 재시작하면 초기화됨)
GUARDIAN_LINKS = {}  # {code: {"linked": bool, "permissions": dict}}
# 복약 기록 저장소 (메모리 기반) - key는 어르신의 elder_code
MEDICATION_RECORDS = {}  # {code: [{"date":.., "medicineName":..}, ...]}

# ---------------------------------------------------------
# 가짜 DB
# ---------------------------------------------------------
MEDICINES = {
    "1": {
        "id": "1",
        "name": "노바스크정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용",
            "effect": "혈압을 낮추는 약입니다.",
            "precautions": "임의로 끊지 마세요.\n일어날 때 천천히 움직이세요.",
            "emergencySigns": [
                "심한 어지러움",
                "호흡곤란",
                "실신"
            ],
            "interactions": [
                "다른 혈압약",
                "발기부전 치료제"
            ]
        },
        "hasAudio": True
    },
    "2": {
        "id": "2",
        "name": "아모디핀정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용",
            "effect": "혈압을 낮추는 약입니다.",
            "precautions": "임의로 끊지 마세요.\n일어날 때 천천히 움직이세요.",
            "emergencySigns": [
                "심한 어지러움",
                "호흡곤란",
                "실신"
            ],
            "interactions": [
                "다른 혈압약",
                "발기부전 치료제"
            ]
        },
        "hasAudio": True
    },
    "3": {
        "id": "3",
        "name": "암로디핀정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용",
            "effect": "혈압을 낮추는 약입니다.",
            "precautions": "임의로 끊지 마세요.\n일어날 때 천천히 움직이세요.",
            "emergencySigns": [
                "심한 어지러움",
                "호흡곤란",
                "실신"
            ],
            "interactions": [
                "다른 혈압약",
                "발기부전 치료제"
            ]
        },
        "hasAudio": True
    },
    "4": {
        "id": "4",
        "name": "코자정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추고 신장을 보호하는 약입니다. 하루 1회 드세요.",
        "rawInfo": {
            "usage": "하루 1회\n식사와 관계없이 복용",
            "effect": "혈압을 낮추고 신장을 보호하는 약입니다.",
            "precautions": "칼륨 영양제는 의사와 상담 후 복용하세요.\n탈수 시 어지러울 수 있습니다.",
            "emergencySigns": [
                "소변이 잘 나오지 않음",
                "심한 어지러움"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "칼륨 보충제"
            ]
        },
        "hasAudio": True
    },
    "5": {
        "id": "5",
        "name": "로자탄정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추고 신장을 보호하는 약입니다. 하루 1회 드세요.",
        "rawInfo": {
            "usage": "하루 1회\n식사와 관계없이 복용",
            "effect": "혈압을 낮추고 신장을 보호하는 약입니다.",
            "precautions": "칼륨 영양제는 의사와 상담 후 복용하세요.\n탈수 시 어지러울 수 있습니다.",
            "emergencySigns": [
                "소변이 잘 나오지 않음",
                "심한 어지러움"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "칼륨 보충제"
            ]
        },
        "hasAudio": True
    },
    "6": {
        "id": "6",
        "name": "로사르탄정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추고 신장을 보호하는 약입니다. 하루 1회 드세요.",
        "rawInfo": {
            "usage": "하루 1회\n식사와 관계없이 복용",
            "effect": "혈압을 낮추고 신장을 보호하는 약입니다.",
            "precautions": "칼륨 영양제는 의사와 상담 후 복용하세요.\n탈수 시 어지러울 수 있습니다.",
            "emergencySigns": [
                "소변이 잘 나오지 않음",
                "심한 어지러움"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "칼륨 보충제"
            ]
        },
        "hasAudio": True
    },
    "7": {
        "id": "7",
        "name": "디오반정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추고 심장을 보호하는 약입니다. 하루 1회 드세요.",
        "rawInfo": {
            "usage": "하루 1회\n식사와 관계없이 복용",
            "effect": "혈압을 낮추고 심장을 보호하는 약입니다.",
            "precautions": "임의로 중단하지 마세요.\n탈수되지 않도록 충분히 수분을 섭취하세요.",
            "emergencySigns": [
                "실신",
                "심한 어지러움"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "칼륨 보충제"
            ]
        },
        "hasAudio": True
    },
    "8": {
        "id": "8",
        "name": "미카르디스정",
        "category": "고혈압",
        "easyExplanation": "혈압을 낮추고 심혈관 질환 위험을 줄이는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용",
            "effect": "혈압을 낮추고 심혈관 질환 위험을 줄이는 약입니다.",
            "precautions": "갑자기 일어나지 마세요.\n혈압을 꾸준히 확인하세요.",
            "emergencySigns": [
                "실신",
                "호흡곤란",
                "얼굴이 심하게 붓는 경우"
            ],
            "interactions": [
                "칼륨 보충제",
                "이부프로펜",
                "나프록센"
            ]
        },
        "hasAudio": True
    },
    "9": {
        "id": "9",
        "name": "다이아벡스정",
        "category": "당뇨",
        "easyExplanation": "혈당을 낮추는 당뇨병 치료제입니다. 하루 2~3번 또는 서방정은 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 2~3번 또는 서방정은 하루 1번\n식사와 함께 또는 식후에 복용",
            "effect": "혈당을 낮추는 당뇨병 치료제입니다.",
            "precautions": "식사를 거르지 마세요.\n검사(조영제 사용 CT 등) 전에는 의사에게 복용 중이라고 알려주세요.\n음주는 피하는 것이 좋습니다.",
            "emergencySigns": [
                "심한 구토나 설사",
                "호흡이 가빠짐",
                "심한 무기력감"
            ],
            "interactions": [
                "조영제",
                "과도한 음주"
            ]
        },
        "hasAudio": True
    },
    "10": {
        "id": "10",
        "name": "글루코파지정",
        "category": "당뇨",
        "easyExplanation": "혈당을 낮추는 당뇨병 치료제입니다. 하루 2~3번 또는 서방정은 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 2~3번 또는 서방정은 하루 1번\n식사와 함께 또는 식후에 복용",
            "effect": "혈당을 낮추는 당뇨병 치료제입니다.",
            "precautions": "식사를 거르지 마세요.\n검사(조영제 사용 CT 등) 전에는 의사에게 복용 중이라고 알려주세요.\n음주는 피하는 것이 좋습니다.",
            "emergencySigns": [
                "심한 구토나 설사",
                "호흡이 가빠짐",
                "심한 무기력감"
            ],
            "interactions": [
                "조영제",
                "과도한 음주"
            ]
        },
        "hasAudio": True
    },
    "11": {
        "id": "11",
        "name": "아마릴정",
        "category": "당뇨",
        "easyExplanation": "혈당을 낮추는 당뇨병 치료제입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n아침 식사 직전 또는 식사와 함께 복용",
            "effect": "혈당을 낮추는 당뇨병 치료제입니다.",
            "precautions": "약을 먹고 식사를 거르면 저혈당이 생길 수 있습니다.\n사탕이나 주스를 준비해 두는 것이 좋습니다.",
            "emergencySigns": [
                "의식이 흐려짐",
                "심한 식은땀",
                "경련",
                "의식 소실"
            ],
            "interactions": [
                "술",
                "다른 당뇨약",
                "일부 항생제(의사·약사 상담)"
            ]
        },
        "hasAudio": True
    },
    "12": {
        "id": "12",
        "name": "포시가정",
        "category": "당뇨",
        "easyExplanation": "소변으로 당을 배출하여 혈당을 낮추는 당뇨병 치료제입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "소변으로 당을 배출하여 혈당을 낮추는 당뇨병 치료제입니다.",
            "precautions": "물을 충분히 마시세요.\n소변을 자주 볼 수 있습니다.\n생식기 위생을 청결하게 유지하세요.",
            "emergencySigns": [
                "심한 탈수",
                "심한 복통",
                "생식기 통증이나 심한 염증"
            ],
            "interactions": [
                "이뇨제",
                "다른 당뇨약(저혈당 위험 증가)"
            ]
        },
        "hasAudio": True
    },
    "13": {
        "id": "13",
        "name": "자디앙정",
        "category": "당뇨",
        "easyExplanation": "혈당을 낮추고 심장과 신장을 보호하는 당뇨병 치료제입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "혈당을 낮추고 심장과 신장을 보호하는 당뇨병 치료제입니다.",
            "precautions": "충분한 수분을 섭취하세요.\n소변량이 늘어날 수 있습니다.\n몸이 아프거나 탈수가 심하면 의사와 상담하세요.",
            "emergencySigns": [
                "심한 탈수",
                "호흡이 가빠짐",
                "심한 복통",
                "의식이 흐려짐"
            ],
            "interactions": [
                "이뇨제",
                "다른 당뇨약",
                "과도한 음주"
            ]
        },
        "hasAudio": True
    },
    "14": {
        "id": "14",
        "name": "리피토정",
        "category": "고지혈증",
        "easyExplanation": "콜레스테롤을 낮춰 심근경색과 뇌졸중을 예방하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "콜레스테롤을 낮춰 심근경색과 뇌졸중을 예방하는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n근육통이나 근육 약화가 나타나면 의사와 상담하세요.\n정기적인 혈액검사를 받는 것이 좋습니다.",
            "emergencySigns": [
                "심한 근육통",
                "소변 색이 갈색으로 변함",
                "피부나 눈이 노랗게 변함"
            ],
            "interactions": [
                "일부 항생제(클래리스로마이신 등)",
                "일부 항진균제",
                "자몽주스 과다 섭취"
            ]
        },
        "hasAudio": True
    },
    "15": {
        "id": "15",
        "name": "크레스토정",
        "category": "고지혈증",
        "easyExplanation": "콜레스테롤을 낮춰 심혈관 질환을 예방하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "콜레스테롤을 낮춰 심혈관 질환을 예방하는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n근육통이나 심한 피로감이 있으면 의사와 상담하세요.",
            "emergencySigns": [
                "심한 근육통",
                "소변 색이 갈색으로 변함",
                "피부나 눈이 노랗게 변함"
            ],
            "interactions": [
                "일부 항생제",
                "일부 항진균제",
                "와파린(의사 상담 필요)"
            ]
        },
        "hasAudio": True
    },
    "16": {
        "id": "16",
        "name": "아스트릭스캡슐",
        "category": "혈전 예방",
        "easyExplanation": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식후에 충분한 물과 함께 복용",
            "effect": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n출혈이 오래 지속되거나 멍이 쉽게 생길 수 있습니다.\n수술이나 치과 치료 전에는 복용 사실을 알려주세요.",
            "emergencySigns": [
                "검은색 변",
                "피를 토함",
                "멈추지 않는 출혈",
                "심한 복통"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "와파린",
                "클로피도그렐(의사 처방 없이 함께 복용 금지)"
            ]
        },
        "hasAudio": True
    },
    "17": {
        "id": "17",
        "name": "바이아스피린정",
        "category": "혈전 예방",
        "easyExplanation": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식후에 충분한 물과 함께 복용",
            "effect": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n출혈이 오래 지속되거나 멍이 쉽게 생길 수 있습니다.\n수술이나 치과 치료 전에는 복용 사실을 알려주세요.",
            "emergencySigns": [
                "검은색 변",
                "피를 토함",
                "멈추지 않는 출혈",
                "심한 복통"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "와파린",
                "클로피도그렐(의사 처방 없이 함께 복용 금지)"
            ]
        },
        "hasAudio": True
    },
    "18": {
        "id": "18",
        "name": "플라빅스정",
        "category": "혈전 예방",
        "easyExplanation": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "혈전 생성을 막아 심근경색과 뇌졸중을 예방하는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n멍이 쉽게 생기거나 출혈이 오래 지속될 수 있습니다.\n수술이나 치과 치료 전에는 복용 사실을 알려주세요.",
            "emergencySigns": [
                "멈추지 않는 출혈",
                "검은색 변",
                "피를 토함",
                "갑작스러운 심한 두통이나 의식 저하"
            ],
            "interactions": [
                "이부프로펜",
                "나프록센",
                "와파린",
                "오메프라졸(일부 위장약, 의사와 상담 필요)"
            ]
        },
        "hasAudio": True
    },
    "19": {
        "id": "19",
        "name": "넥시움정",
        "category": "위장약",
        "easyExplanation": "위산을 줄여 위궤양, 역류성 식도염, 속쓰림을 치료하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사 30~60분 전에 복용",
            "effect": "위산을 줄여 위궤양, 역류성 식도염, 속쓰림을 치료하는 약입니다.",
            "precautions": "의사와 상의 없이 장기간 복용하지 마세요.\n증상이 좋아져도 임의로 중단하지 마세요.",
            "emergencySigns": [
                "심한 복통",
                "피를 토하거나 검은색 변이 나오는 경우",
                "심한 알레르기 증상"
            ],
            "interactions": [
                "클로피도그렐(플라빅스정)",
                "일부 항진균제(케토코나졸 등)"
            ]
        },
        "hasAudio": True
    },
    "20": {
        "id": "20",
        "name": "판토록정",
        "category": "위장약",
        "easyExplanation": "위산을 줄여 위궤양과 역류성 식도염을 치료하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사 30~60분 전에 복용",
            "effect": "위산을 줄여 위궤양과 역류성 식도염을 치료하는 약입니다.",
            "precautions": "장기간 복용은 의사와 상담하세요.\n증상이 계속되면 병원을 방문하세요.",
            "emergencySigns": [
                "심한 복통",
                "피를 토하거나 검은색 변이 나오는 경우",
                "심한 알레르기 증상"
            ],
            "interactions": [
                "일부 항진균제(케토코나졸 등)",
                "메토트렉세이트(고용량 사용 시)"
            ]
        },
        "hasAudio": True
    },
    "21": {
        "id": "21",
        "name": "타이레놀정",
        "category": "진통제",
        "easyExplanation": "통증을 완화하고 열을 내리는 약입니다. 필요할 때 복용 드세요.",
        "rawInfo": {
            "usage": "필요할 때 복용\n제품에 표시된 복용량과 복용 간격을 지키기",
            "effect": "통증을 완화하고 열을 내리는 약입니다.",
            "precautions": "하루 최대 복용량을 초과하지 마세요.\n술을 자주 마시는 경우 복용 전 의사·약사와 상담하세요.\n감기약에도 같은 성분이 들어 있을 수 있으므로 중복 복용하지 마세요.",
            "emergencySigns": [
                "심한 복통",
                "피부 발진이나 호흡곤란",
                "피부나 눈이 노랗게 변하는 경우"
            ],
            "interactions": [
                "다른 아세트아미노펜 함유 약(감기약 등)",
                "과도한 음주",
                "와파린(장기간 함께 복용 시 주의)"
            ]
        },
        "hasAudio": True
    },
    "22": {
        "id": "22",
        "name": "쎄레브렉스캡슐",
        "category": "진통소염제",
        "easyExplanation": "관절염, 근육통 등의 통증과 염증을 완화하는 약입니다. 하루 1~2회 드세요.",
        "rawInfo": {
            "usage": "하루 1~2회\n식사와 관계없이 복용 가능(속이 불편하면 식후 복용)",
            "effect": "관절염, 근육통 등의 통증과 염증을 완화하는 약입니다.",
            "precautions": "장기간 복용하지 마세요.\n심장병, 고혈압이 있다면 의사와 상담하세요.\n탈수 상태에서는 주의하세요.",
            "emergencySigns": [
                "검은색 변",
                "피를 토함",
                "심한 흉통",
                "호흡곤란"
            ],
            "interactions": [
                "아스피린",
                "클로피도그렐",
                "와파린",
                "다른 소염진통제(NSAIDs)"
            ]
        },
        "hasAudio": True
    },
    "23": {
        "id": "23",
        "name": "낙센정",
        "category": "진통소염제",
        "easyExplanation": "관절염, 근육통, 허리 통증 등의 통증과 염증을 완화하는 약입니다. 식후에 충분한 물과 함께 복용 드세요.",
        "rawInfo": {
            "usage": "식후에 충분한 물과 함께 복용",
            "effect": "관절염, 근육통, 허리 통증 등의 통증과 염증을 완화하는 약입니다.",
            "precautions": "공복 복용은 피하세요.\n위궤양이나 위출혈 병력이 있으면 의사와 상담하세요.\n장기간 복용하지 마세요.",
            "emergencySigns": [
                "검은색 변",
                "피를 토함",
                "심한 복통",
                "호흡곤란"
            ],
            "interactions": [
                "아스피린",
                "클로피도그렐",
                "와파린",
                "다른 소염진통제(NSAIDs)"
            ]
        },
        "hasAudio": True
    },
    "24": {
        "id": "24",
        "name": "포사맥스정",
        "category": "골다공증",
        "easyExplanation": "골다공증을 치료하고 골절을 예방하는 약입니다. 아침 공복에 충분한 물과 함께 복용 드세요.",
        "rawInfo": {
            "usage": "아침 공복에 충분한 물과 함께 복용\n복용 후 30분 이상 눕지 않기\n복용 후 30분 동안 음식이나 다른 약은 먹지 않기",
            "effect": "골다공증을 치료하고 골절을 예방하는 약입니다.",
            "precautions": "반드시 물 한 컵 이상과 함께 복용하세요.\n식도 질환이 있는 경우 의사와 상담하세요.",
            "emergencySigns": [
                "심한 가슴 통증",
                "삼키기 어려움",
                "심한 속쓰림"
            ],
            "interactions": [
                "칼슘제",
                "철분제",
                "제산제",
                "우유(복용 직후)"
            ]
        },
        "hasAudio": True
    },
    "25": {
        "id": "25",
        "name": "악토넬정",
        "category": "골다공증",
        "easyExplanation": "골다공증을 치료하고 골절을 예방하는 약입니다. 아침 공복에 충분한 물과 함께 복용 드세요.",
        "rawInfo": {
            "usage": "아침 공복에 충분한 물과 함께 복용\n복용 후 30분 이상 눕지 않기\n복용 후 30분 동안 음식이나 다른 약은 먹지 않기",
            "effect": "골다공증을 치료하고 골절을 예방하는 약입니다.",
            "precautions": "반드시 물 한 컵 이상과 함께 복용하세요.\n임의로 복용을 중단하지 마세요.",
            "emergencySigns": [
                "심한 가슴 통증",
                "삼키기 어려움",
                "심한 속쓰림"
            ],
            "interactions": [
                "칼슘제",
                "철분제",
                "제산제",
                "우유(복용 직후)"
            ]
        },
        "hasAudio": True
    },
    "26": {
        "id": "26",
        "name": "아리셉트정",
        "category": "치매",
        "easyExplanation": "치매 증상을 완화하고 기억력과 인지기능 유지에 도움을 주는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n보통 취침 전에 복용",
            "effect": "치매 증상을 완화하고 기억력과 인지기능 유지에 도움을 주는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n어지러움이 있을 수 있으므로 넘어지지 않도록 주의하세요.",
            "emergencySigns": [
                "심한 어지러움이나 실신",
                "심한 구토",
                "호흡곤란"
            ],
            "interactions": [
                "감기약(항히스타민 성분)",
                "다른 치매약",
                "일부 심장약"
            ]
        },
        "hasAudio": True
    },
    "27": {
        "id": "27",
        "name": "에빅사정",
        "category": "치매",
        "easyExplanation": "치매 증상을 완화하고 일상생활 기능 유지에 도움을 주는 약입니다. 하루 1~2회 드세요.",
        "rawInfo": {
            "usage": "하루 1~2회\n식사와 관계없이 복용 가능",
            "effect": "치매 증상을 완화하고 일상생활 기능 유지에 도움을 주는 약입니다.",
            "precautions": "임의로 복용을 중단하지 마세요.\n어지럽거나 졸릴 수 있으니 넘어지지 않도록 주의하세요.",
            "emergencySigns": [
                "심한 어지러움",
                "의식이 흐려짐",
                "환각이나 이상행동이 심해지는 경우"
            ],
            "interactions": [
                "아만타딘",
                "케타민",
                "덱스트로메토르판(일부 감기약)"
            ]
        },
        "hasAudio": True
    },
    "28": {
        "id": "28",
        "name": "렉사프로정",
        "category": "우울증",
        "easyExplanation": "우울증과 불안 증상을 완화하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "우울증과 불안 증상을 완화하는 약입니다.",
            "precautions": "효과가 나타나기까지 2~4주 정도 걸릴 수 있습니다.\n임의로 복용을 중단하지 마세요.\n졸리거나 어지러울 수 있습니다.",
            "emergencySigns": [
                "극심한 불안이나 초조함",
                "의식 저하",
                "호흡곤란",
                "심한 발진"
            ],
            "interactions": [
                "다른 항우울제",
                "트라마돌",
                "세인트존스워트(건강기능식품)"
            ]
        },
        "hasAudio": True
    },
    "29": {
        "id": "29",
        "name": "졸로푸트정",
        "category": "우울증",
        "easyExplanation": "우울증과 불안 증상을 완화하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "우울증과 불안 증상을 완화하는 약입니다.",
            "precautions": "효과가 나타나기까지 2~4주 정도 걸릴 수 있습니다.\n임의로 복용을 중단하지 마세요.\n졸리거나 어지러울 수 있습니다.",
            "emergencySigns": [
                "심한 불안이나 초조함",
                "발열과 근육 경직",
                "의식 저하",
                "호흡곤란"
            ],
            "interactions": [
                "다른 항우울제",
                "트라마돌",
                "세인트존스워트(건강기능식품)",
                "와파린(출혈 위험 증가)"
            ]
        },
        "hasAudio": True
    },
    "30": {
        "id": "30",
        "name": "스틸녹스정",
        "category": "수면제",
        "easyExplanation": "불면증 치료를 돕는 수면제입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n잠자기 직전에 복용",
            "effect": "불면증 치료를 돕는 수면제입니다.",
            "precautions": "약을 먹은 후 바로 잠자리에 드세요.\n다음 날 졸릴 수 있으므로 운전이나 위험한 작업은 피하세요.\n임의로 용량을 늘리거나 장기간 복용하지 마세요.",
            "emergencySigns": [
                "이상행동(몽유병, 기억이 나지 않는 행동)",
                "호흡곤란",
                "심한 어지러움이나 의식 저하"
            ],
            "interactions": [
                "술",
                "다른 수면제",
                "진정제",
                "마약성 진통제"
            ]
        },
        "hasAudio": True
    },
    "31": {
        "id": "31",
        "name": "하루날디정",
        "category": "전립선비대증",
        "easyExplanation": "전립선비대증으로 인한 소변 불편 증상을 완화하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n매일 같은 식사 후(보통 아침 식후) 복용",
            "effect": "전립선비대증으로 인한 소변 불편 증상을 완화하는 약입니다.",
            "precautions": "갑자기 일어나면 어지러울 수 있으니 천천히 움직이세요.\n임의로 복용을 중단하지 마세요.",
            "emergencySigns": [
                "실신",
                "심한 어지러움",
                "알레르기 반응(얼굴이나 입술이 붓는 경우)"
            ],
            "interactions": [
                "다른 혈압약",
                "발기부전 치료제(실데나필, 타다라필)"
            ]
        },
        "hasAudio": True
    },
    "32": {
        "id": "32",
        "name": "아보다트연질캡슐",
        "category": "전립선비대증",
        "easyExplanation": "전립선 크기를 줄여 배뇨 증상을 개선하는 약입니다. 하루 1번 드세요.",
        "rawInfo": {
            "usage": "하루 1번\n식사와 관계없이 복용 가능",
            "effect": "전립선 크기를 줄여 배뇨 증상을 개선하는 약입니다.",
            "precautions": "효과가 나타나기까지 몇 달이 걸릴 수 있으므로 꾸준히 복용하세요.\n임의로 복용을 중단하지 마세요.",
            "emergencySigns": [
                "심한 알레르기 반응",
                "가슴에 멍울이나 통증이 생기는 경우"
            ],
            "interactions": [
                "일부 항진균제",
                "일부 항생제(의사·약사 상담)"
            ]
        },
        "hasAudio": True
    },
    "33": {
        "id": "33",
        "name": "듀파락이지시럽",
        "category": "변비",
        "easyExplanation": "변비를 완화하는 변비약입니다. 하루 1~2회 드세요.",
        "rawInfo": {
            "usage": "하루 1~2회\n물과 함께 복용하면 도움이 됨",
            "effect": "변비를 완화하는 변비약입니다.",
            "precautions": "충분한 물을 함께 마시세요.\n설사가 심하면 복용을 중단하고 의사와 상담하세요.",
            "emergencySigns": [
                "심한 복통",
                "심한 설사",
                "혈변"
            ],
            "interactions": [
                "다른 변비약(과다 복용 주의)"
            ]
        },
        "hasAudio": True
    },
    "34": {
        "id": "34",
        "name": "마그밀정",
        "category": "변비",
        "easyExplanation": "변비를 완화하고 위산을 중화하는 약입니다. 충분한 물과 함께 복용 드세요.",
        "rawInfo": {
            "usage": "충분한 물과 함께 복용\n다른 약과는 2시간 이상 간격을 두고 복용",
            "effect": "변비를 완화하고 위산을 중화하는 약입니다.",
            "precautions": "장기간 계속 복용하지 마세요.\n신장질환이 있는 경우 의사와 상담하세요.",
            "emergencySigns": [
                "심한 설사",
                "심한 복통",
                "근육 약화나 심한 무기력감"
            ],
            "interactions": [
                "항생제(테트라사이클린계, 퀴놀론계)",
                "철분제",
                "골다공증 치료제(알렌드로네이트, 리세드로네이트)"
            ]
        },
        "hasAudio": True
    }
}


def ok(data):
    return jsonify({"success": True, "data": data, "error": None})


def fail(code, message, status=400):
    return jsonify({"success": False, "data": None, "error": {"code": code, "message": message}}), status


# ---------------------------------------------------------
# POST /medicines/scan
# ---------------------------------------------------------
@app.route("/medicines/scan", methods=["POST"])
def scan():
    file = request.files.get("image")
    if file is None:
        return fail("NO_IMAGE", "이미지가 없어요.")

    filename = file.filename or ""
    # 확장자 제거
    stem = filename.rsplit(".", 1)[0]

    # 1) 정확히 상품명과 일치 → matched
    for med in MEDICINES.values():
        if stem == med["name"]:
            return ok({"matchStatus": "matched", "medicine": med, "candidates": []})

    # 2) category와 일치 → multiple_candidates
    matched_candidates = [m for m in MEDICINES.values() if stem == m["category"]]
    if matched_candidates:
        candidates = [{"id": m["id"], "name": m["name"], "category": m["category"]} for m in matched_candidates]
        return ok({"matchStatus": "multiple_candidates", "medicine": None, "candidates": candidates})

    # 3) 그 외 → not_found
    return ok({"matchStatus": "not_found", "medicine": None, "candidates": []})


# ---------------------------------------------------------
# GET /medicines/<id>
# ---------------------------------------------------------
@app.route("/medicines/<medicine_id>", methods=["GET"])
def detail(medicine_id):
    med = MEDICINES.get(medicine_id)
    if med is None:
        return fail("NOT_FOUND", "해당 약을 찾을 수 없어요.", status=404)
    return ok(med)


# ---------------------------------------------------------
# GET /medicines/<id>/audio
# CLOVA Voice 대신 gTTS 사용. 같은 약은 최초 1회만 생성하고 캐싱된 파일 재사용.
# ---------------------------------------------------------
@app.route("/medicines/<medicine_id>/audio", methods=["GET"])
def audio(medicine_id):
    med = MEDICINES.get(medicine_id)
    if med is None:
        return fail("NOT_FOUND", "해당 약을 찾을 수 없어요.", status=404)
    if not med.get("hasAudio"):
        return fail("NO_AUDIO", "음성이 준비되지 않았어요.")

    filename = f"{medicine_id}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)

    # 캐싱: 이미 만들어둔 파일이 있으면 재생성하지 않음 (gTTS 호출 횟수/시간 절감)
    if not os.path.exists(filepath):
        text = f"{med['name']}. {med['easyExplanation']}"
        try:
            tts = gTTS(text=text, lang="ko")
            tts.save(filepath)
        except Exception as e:
            return fail("TTS_ERROR", f"음성 생성 중 오류가 발생했어요: {e}", status=500)

    audio_url = f"{request.host_url.rstrip('/')}/audio_cache/{filename}"
    return ok({"audioUrl": audio_url})


@app.route("/audio_cache/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


# ---------------------------------------------------------
# GET /medicines/search?query=...
# ---------------------------------------------------------
@app.route("/medicines/search", methods=["GET"])
def search():
    query = (request.args.get("query") or request.args.get("keyword") or "").strip()
    if not query:
        return ok({"results": []})

    results = [
        {"id": m["id"], "name": m["name"], "category": m["category"]}
        for m in MEDICINES.values()
        if query in m["name"] or query in m["category"]
    ]
    return ok({"results": results})


# ---------------------------------------------------------
# 보호자 연결 기능 (임시 mock - 실제 백엔드 나오면 교체 예정)
# ---------------------------------------------------------
@app.route("/guardian/code", methods=["POST"])
def create_guardian_code():
    code = f"{random.randint(0, 999999):06d}"
    GUARDIAN_LINKS[code] = {"linked": False, "permissions": None}
    return ok({"code": code})


@app.route("/guardian/verify", methods=["POST"])
def verify_guardian_code():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip()
    permissions = data.get("permissions", {})

    link = GUARDIAN_LINKS.get(code)
    if link is None:
        return fail("INVALID_CODE", "유효하지 않은 코드예요.", status=404)

    link["linked"] = True
    link["permissions"] = permissions
    return ok({"code": code, "permissions": permissions})


@app.route("/guardian/<code>/records", methods=["GET"])
def get_guardian_records(code):
    link = GUARDIAN_LINKS.get(code)
    if link is None or not link.get("linked"):
        return fail("NOT_LINKED", "연동되지 않은 코드예요.", status=404)
    records = MEDICATION_RECORDS.get(code, [])
    return ok({"records": records})


# ---------------------------------------------------------
# 복약 기록 저장 (임시 mock)
# ---------------------------------------------------------
@app.route("/medication/record", methods=["POST"])
def add_medication_record():
    data = request.get_json(force=True, silent=True) or {}
    code = data.get("code")
    date = data.get("date")
    medicine_name = data.get("medicineName")

    if not code:
        return fail("NO_CODE", "코드가 필요해요.")

    MEDICATION_RECORDS.setdefault(code, []).append({"date": date, "medicineName": medicine_name})
    return ok({"saved": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
