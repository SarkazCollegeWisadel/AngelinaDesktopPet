from __future__ import annotations

APP_NAME = "安洁莉娜桌宠"
APP_ID = "AngelinaDesktopPet"
ORGANIZATION = "LocalAngelinaPet"

MIN_HEIGHT = 120
MAX_HEIGHT = 700
DEFAULT_HEIGHT = 300

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# The user's Step Plan subscription uses this dedicated path. Step 3.7 supports
# image input; router-v1 does not, so screen understanding defaults to 3.7.
DEFAULT_STEP_BASE_URL = "https://api.stepfun.com/step_plan/v1"
DEFAULT_STEP_MODEL = "step-3.7-flash"
DEFAULT_TEXT_BASE_URL = DEFAULT_STEP_BASE_URL
DEFAULT_TEXT_MODEL = DEFAULT_STEP_MODEL

IDLE_SCENE = "坐坐"
READING_SCENE = "看书"
OFFICE_SCENE = "办公"

# Facing direction in the source artwork: -1 = left, 1 = right.  The walk
# controller compares the desired travel direction with this value instead of
# assuming every illustration was drawn facing right.
SCENE_SOURCE_FACING = {
    "送货": -1,
    "骑行": 1,
    "纸飞机": -1,
}
LOCOMOTION_SCENES = tuple(SCENE_SOURCE_FACING)
ALL_CHARACTER_SCENES = (
    "购物",
    "海边",
    "看书",
    "拍照",
    "骑行",
    "潜水",
    "送货",
    "探险",
    "纸飞机",
    "坐坐",
)
