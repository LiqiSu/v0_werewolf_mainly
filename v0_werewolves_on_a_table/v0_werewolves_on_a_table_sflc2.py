import os
import json
import uuid
from datetime import datetime
from groq import Groq
import random
import copy

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"

DATA_DIR = "data"
WORLD_BIBLE_FILE = os.path.join(DATA_DIR, "world_bible.json")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.json")
SCENE_STATE_FILE = os.path.join(DATA_DIR, "scene_state.json")
GAME_ROUNDS_FILE = os.path.join(DATA_DIR, "game_rounds.json")

STYLE_GUIDE_FILE = os.path.join(DATA_DIR, "style_guide.txt")
PLAYER_FILE = os.path.join(DATA_DIR, "player.json")

SHORT_MEMORY_FILE = os.path.join(DATA_DIR, "memory_short.json")
MEDIUM_MEMORY_FILE = os.path.join(DATA_DIR, "memory_medium.json")
LONG_ARCHIVE_FILE = os.path.join(DATA_DIR, "memory_long_archive.json")
LONG_SUMMARY_FILE = os.path.join(DATA_DIR, "long_term_summary.txt")

EVENT_LOG_FILE = os.path.join(DATA_DIR, "event_log.txt")
CHAPTER_LOG_FILE = os.path.join(DATA_DIR, "chapters.txt")

os.makedirs(DATA_DIR, exist_ok=True)

client = Groq(api_key=API_KEY)

# ALL try-except is without error messages printing
# some don't have try-except
# low error tolerance now
# hugely relying on LLM to output exactly correct structure/format
# unstable, risky
# prone to drift and corrupt overtime
# high entropy
# ABOUT NAMES, KEY NAMES, very important. CONSIDER UUID FOR...WHICH THINGS...?

# =========================
# FILE HELPERS
# =========================
def load_json(path, default):
    if not os.path.exists(path):
        return copy.deepcopy(default)
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return copy.deepcopy(default)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_text(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def append_text(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")
        
# =========================
# MORE HELPERS
# =========================
def clamp_int(value, min_val, max_val, default=None):
    try:
        v = int(value)
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default if default is not None else min_val

def deep_merge_dict(base, updates):
    """
    Recursively merge dictionaries.
    Only updates provided keys.
    Does not delete missing keys.
    """
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge_dict(base[k], v)
        else:
            base[k] = v
    return base

# =========================
# INITIALIZE FILES IF MISSING
# =========================
def init_files():
    # Create empty files if missing, but do NOT fill defaults
    if not os.path.exists(WORLD_BIBLE_FILE):
        save_json(WORLD_BIBLE_FILE, {})

    if not os.path.exists(CHARACTERS_FILE):
        save_json(CHARACTERS_FILE, {"characters": {}})

    if not os.path.exists(SCENE_STATE_FILE):
        save_json(SCENE_STATE_FILE, {})
    
    if not os.path.exists(GAME_ROUNDS_FILE):
        save_json(GAME_ROUNDS_FILE, {})

    if not os.path.exists(STYLE_GUIDE_FILE):
        save_text(STYLE_GUIDE_FILE, "")

    if not os.path.exists(PLAYER_FILE):
        save_json(PLAYER_FILE, {"player_character": ""})

    if not os.path.exists(SHORT_MEMORY_FILE):
        save_json(SHORT_MEMORY_FILE, {"summaries": []})

    if not os.path.exists(MEDIUM_MEMORY_FILE):
        save_json(MEDIUM_MEMORY_FILE, {"summaries": []})

    if not os.path.exists(LONG_ARCHIVE_FILE):
        save_json(LONG_ARCHIVE_FILE, {"summaries": []})

    if not os.path.exists(LONG_SUMMARY_FILE):
        save_text(LONG_SUMMARY_FILE, "The story has not begun yet.")

    if not os.path.exists(EVENT_LOG_FILE):
        save_text(EVENT_LOG_FILE, "")

    if not os.path.exists(CHAPTER_LOG_FILE):
        save_text(CHAPTER_LOG_FILE, "")

# =========================
# ESTIMATE IN-WORLD TIME PASSAGE
# =========================
# BIG PROBLEM HERE. SOLUTION??? NEED TO ATTEND TO LATER!!!
def estimate_time_from_events(events):
    return 1.0

def update_time_of_day(current, hours):
    cycle = ["morning", "afternoon", "evening", "night"]
    if current not in cycle:
        return "day"
    idx = cycle.index(current)
    if hours > 6:
        idx = (idx + 1) % len(cycle)
    return cycle[idx]

# =========================
# GROQ CALL: CHARACTER DECISION-MAKING AND ACTION BASED ON PERCEPTION
# =========================
def event_template():
    return {
        "type": "",          # thought | speech | action
        "actor": "",
        "target": [],        # can be multiple

        "content": "",       # thoughts/speeches/actions descriptions

        "metadata": {
            "intensity": 0,   # placeholder for now
        }
    }

def attach_event_id(event):
    event["id"] = str(uuid.uuid4())
    return event

def normalize_and_validate_event(e):
    if not isinstance(e, dict):
        return None
    if e.get("type") not in ["thought", "speech", "action", "visual_snapshot"]:
        return None
    if not isinstance(e.get("actor"), str) or not e["actor"]:
        return None
    
    # ---- normalize target ----
    t = e.get("target")
    if isinstance(t, str) and t.strip():
        t = [t.strip()]
    elif isinstance(t, list):
        t = [str(x).strip() for x in t if str(x).strip()]
    else:
        t = []
    # how about things like "everyone"/"the group"/"the party"? Note

    # deduplicate
    t = list(dict.fromkeys(t))  # preserves order
    e["target"] = t

    # content
    if not isinstance(e.get("content"), str):
        e["content"] = ""

    # metadata
    if "metadata" not in e or not isinstance(e["metadata"], dict):
        e["metadata"] = {}
    e["metadata"]["intensity"] = clamp_int(e["metadata"].get("intensity", 0), 0, 100, 0)

    return attach_event_id(e)

def convert_output_to_events(char_name, output):
    events = []
    # thoughts
    for t in output.get("thoughts", []):
        events.append({
            "type": "thought",
            "actor": char_name,
            "target": [],
            "content": t,
            "metadata": {"intensity": 0}
        })
    # actions
    for a in output.get("actions", []):
        events.append({
            "type": "action",
            "actor": char_name,
            "target": a.get("target", []),
            "content": a.get("content", ""),
            "metadata": {"intensity": a.get("intensity", 0)}
        })
    # speech
    for s in output.get("speech", []):
        events.append({
            "type": "speech",
            "actor": char_name,
            "target": s.get("target", []),
            "content": s.get("content", ""),
            "metadata": {"intensity": s.get("intensity", 0)}
        })
    return events

# EXTRACT SCENE INFORMATION FOR CHARACTERS
# THE SIMPLEST FOR NOW. NO PHYSICS/VIEWS/ETC.
# OBJECTS???
def extract_public_scene_info(scene):
    return {
        "location": scene.get("location", {}).get("name"),
        "time_of_day": scene.get("time", {}).get("time_of_day"),
        "weather": scene.get("environment", {}).get("weather", {}).get("description"),
        "rules": scene.get("rules", {})
    }

# NOT PERFECT. BUT. WELL.
def compute_scene_dynamics(conflicts):
    if not conflicts:
        return {"danger_level": 0, "tension": 0}

    intensities = [
        clamp_int(c.get("intensity", 0), 0, 100, 0)
        for c in conflicts.values()
    ]

    total = sum(intensities)
    count = len(intensities)
    avg = total / count if count else 0

    danger_level = clamp_int(int(avg), 0, 100, 0)
    tension = clamp_int(int(total / 2), 0, 100, 0)

    return {
        "danger_level": danger_level,
        "tension": tension
    }

# ...VERY same purpose with the above one...but well...for now.
# NEED to be optimized anyway...
def generate_visual_events(scene, chars_all):
    visual_events = []
    scene_chars = scene.get("characters_present", {})

    for observer in scene_chars:
        for target in scene_chars:
            if observer == target:
                continue

            target_data = chars_all["characters"].get(target, {})
            event = {
                "type": "visual_snapshot",
                "actor": target,
                "target": [observer],
                "content": json.dumps({
                    "basics": {
                        "gender": target_data.get("gender"),
                        "age_apparent": target_data.get("age_apparent"),
                        "species": target_data.get("species"),
                        "appearance": target_data.get("appearance", {})
                    },
                    "state": {
                        "location": target_data.get("location"),
                        "activity": target_data.get("activity"),
                        "physical_state": target_data.get("physical_state", {}),
                    }
                }),
                "metadata": {"intensity": 0}
            }
            visual_events.append(attach_event_id(event))

    return visual_events

def build_perception(events, scene):
    # NOW IS USING OBJECTIVE EVENTS, NOT CHARACTER-INTERPRETED PERCEPTIONS
    perception = {}

    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})

    # ---- VISUAL PART (NOT NEEDED FOR NOW) ----
    # visual_events = generate_visual_events(scene, chars_all)
    # merge them into events
    # events = visual_events + events

    scene_chars = set(scene.get("characters_present", {}).keys())

    # initialize ONLY scene characters first
    for c in scene_chars:
        perception[c] = {}
    
    # ---- SCENE_INFO PERCEPTION PART (ALREADY INITIALIZED, NOT NEEDED FOR NOE) ----
    # public_info = extract_public_scene_info(scene)
    # for c in scene_chars:
    #     perception[c] = {
    #         "__scene__": public_info
    #     }

    for event in events:
        eid = event["id"]
        actor = event["actor"]
        targets = set(event.get("target", []))

        # ------------------------
        # 1. SELF PERCEPTION
        # ------------------------
        if actor not in perception:
            perception[actor] = {}
        perception[actor][eid] = {
            "event": event,
            "confidence": 100
        }

        # ------------------------
        # 2. TARGET PERCEPTION
        # ------------------------
        if event["type"] != "thought":
            for t in targets:
                if t not in perception:
                    perception[t] = {}  # allow off-scene characters
                perception[t][eid] = {
                    "event": event,
                    "confidence": 100
                }

        # ------------------------
        # 3. SCENE PERCEPTION (fallback)
        # ------------------------
        if event["type"] != "thought":
            for c in scene_chars:
                if c == actor:
                    continue
                if c in targets:
                    continue  # already handled
                perception[c][eid] = {
                    "event": event,
                    "confidence": 100
                }

    return perception

def character_decision_and_action(character_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    if character_name not in chars_all.get("characters", {}):
        return None
    char_sheet = chars_all["characters"][character_name]

    # -------------------------
    # Simplify perception input
    # -------------------------
    simplified_events = simplify_perception(perceived_events)

    # -------------------------
    # STRICT PROMPT
    # -------------------------
    prompt = (
        "You are a character decision engine.\n\n"
        "You MUST act ONLY based on:\n"
        "- the character sheet\n"
        "- the perceived events\n\n"
        "CRITICAL RULES:\n"
        "1. You DO NOT know anything outside the perception.\n"
        "2. You DO NOT know other characters' thoughts.\n"
        "3. You DO NOT use world knowledge unless already in the character sheet.\n"
        "4. You MUST stay consistent with personality, goals, and state.\n"
        "5. Keep actions small and immediate (one step, not long plans).\n"
        "6. Thoughts and decisions are PRIVATE.\n"
        "7. Speech and actions are PUBLIC.\n\n"
        "You may internally reason freely: Think step by step internally.\n"
        "But DO NOT reveal your reasoning. DO NOT output reasoning.\n"
        "Only output the final structured result.\n"
        "Thoughts should be internal thoughts of the character, not your meta reasoning.\n\n"
        "Return STRICT JSON:\n"
        "{\n"
        "  \"thoughts\": [\"string\"],\n"
        "  \"decisions\": [\"string\"],\n"
        "  \"actions\": [\n"
        "    {\n"
        "      \"type\": \"action\",\n"
        "      \"target\": [\"string\"],\n"
        "      \"content\": \"string\",\n"
        "      \"intensity\": 0-100\n"
        "    }\n"
        "  ],\n"
        "  \"speech\": [\n"
        "    {\n"
        "      \"target\": [\"string\"],\n"
        "      \"content\": \"string\",\n"
        "      \"intensity\": 0-100\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

    payload = {
        "character_name": character_name,
        "character_sheet": char_sheet,
        "perceived_events": simplified_events
    }
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
        ]
    )
    content = response.choices[0].message["content"]
    try:
        return json.loads(content)
    except:
        return None

# =========================
# GROQ CALL: CHARACTER UPDATES
# =========================
def knowledge_template():
    return {
        "characters": {},

        "world": {
            "setting": {},
            "rules": {},
            "factions": {},
            "cultures": {},
            "places": {},
            "events": {}
        },

        "scene": {
            "location": {},
            "time": {},
            "environment": {},
            "rules": {},    # constraints, etc. with description and severity as values
            "dynamics": {
                "danger_level": 0,
                "tension": 0
            },
            "characters_present": {},   # name -> {"focus": 0-100}
            "objects": {},
            "conflicts": {},            # conflict_key -> {...}
            "events": {}                # event_key -> {...}
        },

        "hard_knowledge": {}
    }

def knowledge_character_entry_template():
    return {
        "basics": {
            "gender": {"value": None, "confidence": 0},
            "age_apparent": {"value": None, "confidence": 0},
            "age_actual": {"value": None, "confidence": 0},
            "species": {"value": None, "confidence": 0},
            "aging_rate": {"value": None, "confidence": 0},
            "is_immortal": {"value": None, "confidence": 0},
            "appearance": {"description": "", "confidence": 0}
        },

        "role": {},
        "background": {},
        "interests": {},
        "dislikes": {},
        "goals": {},
        "traits": {},

        "relationships": {},

        "possessions": {},

        "state": {
            "location": {"value": None, "confidence": 0},
            "activity": {"description": "", "confidence": 0},
            "physical": {},
            "mental": {}
        },

        "knowledge_bits": {},

        "game_status": {
            "role": {"value": "", "confidence": 0},
            "team": {"value": "", "confidence": 0},
            "ability": {"value": {}, "confidence": 0},
            "death_count": {"value": {}, "confidence": 0},
            "is_dead": {"value": False, "confidence": 0}
        }
    }

def character_template():
    return {
        "gender": "",
        "age_apparent": None,
        "age_actual": None,
        "species": "",
        "aging_rate": 1.0,
        "is_immortal": False,

        "nicknames": {},

        "role": {},

        "background": {},

        "memory": {
            "recent": {},
            "mid": {}
        },

        "knowledge": knowledge_template(),

        "access": {},

        "properties": {},
        "personality": {},
        "goals": {},
        "abilities": {},
        "interests": {},
        "dislikes": {},
        "habits": {},

        "appearance": {},

        "physical_state": {},
        "mental_state": {},
        "ongoing_processes": {},

        "faction_affiliations": {},

        "possessions": {},

        "relationships": {},

        "clothing": "",
        "location": "",
        "activity": "",

        "game_status": {
            "role": "",
            "team": "",
            "ability": {},
            "death_count": {},
            "is_dead": False
        }
    }

def character_information_extract_prompt():
    return (
        "Schema:\n"
        "{\n"
        "  \"characters\": {\n"
        "    \"Name\": {\n"
        "      \"gender\": \"string (optional)\",\n"
        "      \"age_apparent\": \"number (optional)\",\n"
        "      \"age_actual\": \"number (optional)\",\n"
        "      \"species\": \"string (optional)\",\n"
        "      \"aging_rate\": \"number (optional)\",\n"
        "      \"is_immortal\": \"boolean (optional)\",\n"
        "      \"nicknames\": {\n"
        "        \"nickname\": {\"used_by\": {\"character\": \"0-100\"}}\n"
        "      },\n"
        "      \"role\": {\n"
        "        \"role_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"background\": {\n"
        "        \"event_key\": {\"description\": \"string\", \"impact\": \"0-100\"}\n"
        "      },\n"
        "      \"memory\": {\n"
        "        \"recent\": {\n"
        "          \"event_key\": {\"description\": \"string\", \"impact\": \"0-100\"}\n"
        "        },\n"
        "        \"mid\": {\n"
        "          \"event_key\": {\"description\": \"string\", \"impact\": \"0-100\"}\n"
        "        }\n"
        "      },\n"
        "      \"knowledge\": {\n"
        "        \"characters\": {\n"
        "          \"OtherCharacter\": {\n"
        "            \"basics\": {\n"
        "              \"gender\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
        "              \"age_apparent\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
        "              \"age_actual\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
        "              \"species\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
        "              \"aging_rate\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
        "              \"is_immortal\": {\"value\": \"boolean\", \"confidence\": \"0-100\"},\n"
        "              \"appearance\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"role\": {\n"
        "              \"role_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"traits\": {\n"
        "              \"trait_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"background\": {\n"
        "              \"event_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"interests\": {\n"
        "              \"interest_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"dislikes\": {\n"
        "              \"dislike_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"goals\": {\n"
        "              \"goal_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"relationships\": {\n"
        "              \"OtherCharacter\": {\n"
        "                \"description\": \"string\",\n"
        "                \"sentiment\": \"-100 to 100\",\n"
        "                \"confidence\": \"0-100\"\n"
        "              }\n"
        "            },\n"
        "            \"possessions\": {\n"
        "              \"item_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
        "            },\n"
        "            \"state\": {\n"
        "              \"location\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
        "              \"activity\": {\"description\": \"string\", \"confidence\": \"0-100\"},\n"
        "              \"physical\": {\n"
        "                \"aspect_key\": {\n"
        "                  \"description\": \"string\",\n"
        "                  \"confidence\": \"0-100\"\n"
        "                }\n"
        "              },\n"
        "              \"mental\": {\n"
        "                \"aspect_key\": {\n"
        "                  \"description\": \"string\",\n"
        "                  \"confidence\": \"0-100\"\n"
        "                }\n"
        "              }\n"
        "            },\n"
        "            \"knowledge_bits\": {\n"
        "              \"key\": {\n"
        "                \"description\": \"string\",\n"
        "                \"confidence\": \"0-100\",\n"
        "                \"decay\": \"slow|medium|fast\"\n"
        "              }\n"
        "            }\n"
        "          }\n"
        "        },\n"
        "        \"world\": {},\n"
        "        \"scene\": {},\n"
        "        \"hard_knowledge\": {}\n"
        "      },\n"
        "      \"properties\": {\n"
        "        \"trait_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"personality\": {\n"
        "        \"trait_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"goals\": {\n"
        "        \"goal_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"ongoing_processes\": {\n"
        "        \"process_key\": {\n"
        "          \"description\": \"string\",\n"
        "          \"progress\": \"0-100\",\n"
        "          \"priority\": \"0-100\"\n"
        "        }\n"
        "      },\n"
        "      \"abilities\": {\n"
        "        \"ability_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"interests\": {\n"
        "        \"interest_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"dislikes\": {\n"
        "        \"dislike_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"habits\": {\n"
        "        \"habit_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"appearance\": {\n"
        "        \"aspect\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"physical_state\": {\n"
        "        \"part_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"mental_state\": {\n"
        "        \"emotion_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"faction_affiliations\": {\n"
        "        \"faction_key\": {\"name\": \"string\", \"role\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"possessions\": {\n"
        "        \"item_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"relationships\": {\n"
        "        \"other_character\": {\"description\": \"string\", \"sentiment\": \"0-100\"}\n"
        "      },\n"
        "      \"clothing\": \"string (optional)\",\n"
        "      \"location\": \"string (optional)\",\n"
        "      \"activity\": \"string (optional)\"\n"

        "    }\n"
        "  }\n"
        "}"
    )
# template and prompt are separate
# This WILL drift over time
# Generate the prompt FROM the template?

def merge_weighted_dict(target, updates):
    """
    Merge dict of:
    key -> {description, value}
    """
    for k, v in updates.items():
        if k not in target:
            target[k] = {"description": "", "value": 0}
        if "description" in v and isinstance(v["description"], str):
            target[k]["description"] = v["description"]
        if "value" in v:
            target[k]["value"] = clamp_int(v["value"], 0, 100, 0)

def merge_confidence_value(target, new_value, new_conf):
    if new_value is None:
        return
    old_conf = target.get("confidence", 0)
    # Prefer higher confidence
    if new_conf >= old_conf:
        target["value"] = new_value
    target["confidence"] = max(old_conf, new_conf)

def merge_confidence_description(target, new_desc, new_conf):
    if not new_desc:
        return
    old_conf = target.get("confidence", 0)
    if new_conf >= old_conf or len(new_desc) > len(target.get("description", "")):
        target["description"] = new_desc
    target["confidence"] = max(old_conf, new_conf)

def merge_character_changes(chars, name, changes):
    """
    Reuse the same merge semantics as update_characters_from_output
    """
    if name not in chars["characters"]:
        chars["characters"][name] = character_template()

    char = chars["characters"][name]

    for field, value in changes.items():
        # simple string fields
        if field in ["gender", "clothing", "location", "activity"]:
            if isinstance(value, str) and value.strip():
                char[field] = value.strip()
            continue

        # simple numeric fields
        if field in ["age_apparent", "age_actual"] and isinstance(value, (int, float)):
            char[field] = value
            continue

        # species / aging / immortality
        if field == "species" and isinstance(value, str) and value.strip():
            char["species"] = value.strip()
            continue

        if field == "aging_rate" and isinstance(value, (int, float)):
            char["aging_rate"] = float(value)
            continue

        if field == "is_immortal" and isinstance(value, bool):
            char["is_immortal"] = value
            continue

        # nicknames (dict of dicts)
        if field == "nicknames":
            if "nicknames" not in char or not isinstance(char["nicknames"], dict):
                char["nicknames"] = {}
            for nickname, ndata in value.items():
                if nickname not in char["nicknames"]:
                    char["nicknames"][nickname] = {"used_by": {}}
                if "used_by" in ndata:
                    for user, freq in ndata["used_by"].items():
                        char["nicknames"][nickname]["used_by"][user] = clamp_int(freq, 0, 100, 0)
            continue

        # properties (dict of dicts)
        if field == "properties":
            if "properties" not in char or not isinstance(char["properties"], dict):
                char["properties"] = {}
            for p_key, pdata in value.items():
                if p_key not in char["properties"]:
                    char["properties"][p_key] = {"description": "", "value": 0}
                if "description" in pdata:
                    char["properties"][p_key]["description"] = pdata["description"]
                if "value" in pdata:
                    char["properties"][p_key]["value"] = clamp_int(pdata["value"], 0, 100, 0)
            continue
        
        # description + value fields (function used)
        if field in ["personality", "goals", "abilities", "interests", "dislikes", "habits"]:
            if field not in char or not isinstance(char[field], dict):
                char[field] = {}
            merge_weighted_dict(char[field], value)
            continue

        if field == "appearance":
            if "appearance" not in char or not isinstance(char["appearance"], dict):
                char["appearance"] = {}
            merge_weighted_dict(char["appearance"], value)
            continue

        if field == "role":
            if "role" not in char or not isinstance(char["role"], dict):
                char["role"] = {}
            merge_weighted_dict(char["role"], value)
            continue

        # background (dict of dicts)
        if field == "background":
            if "background" not in char or not isinstance(char["background"], dict):
                char["background"] = {}
            for b_key, b_data in value.items():
                if b_key not in char["background"]:
                    char["background"][b_key] = {"description": "", "impact": 0}
                if "description" in b_data:
                    char["background"][b_key]["description"] = b_data["description"]
                if "impact" in b_data:
                    char["background"][b_key]["impact"] = clamp_int(b_data["impact"], 0, 100, 0)
            continue

        # physical_state (dict of dicts)
        if field == "physical_state":
            if "physical_state" not in char or not isinstance(char["physical_state"], dict):
                char["physical_state"] = {}
            for part, pdata in value.items():
                if part not in char["physical_state"]:
                    char["physical_state"][part] = {"description": "", "value": 0}
                if "description" in pdata:
                    char["physical_state"][part]["description"] = pdata["description"]
                if "value" in pdata:
                    char["physical_state"][part]["value"] = clamp_int(pdata["value"], 0, 100, 0)
            continue

        # mental_state (dict of dicts)
        if field == "mental_state":
            if "mental_state" not in char or not isinstance(char["mental_state"], dict):
                char["mental_state"] = {}
            for emo, edata in value.items():
                if emo not in char["mental_state"]:
                    char["mental_state"][emo] = {"description": "", "value": 0}
                if "description" in edata:
                    char["mental_state"][emo]["description"] = edata["description"]
                if "value" in edata:
                    char["mental_state"][emo]["value"] = clamp_int(edata["value"], 0, 100, 0)
            continue

        # faction_affiliations (dict of dicts)
        if field == "faction_affiliations":
            if "faction_affiliations" not in char or not isinstance(char["faction_affiliations"], dict):
                char["faction_affiliations"] = {}
            for f_key, f_data in value.items():
                if f_key not in char["faction_affiliations"]:
                    char["faction_affiliations"][f_key] = {"name": "", "role": "", "value": 0}
                if "name" in f_data:
                    char["faction_affiliations"][f_key]["name"] = f_data["name"]
                if "role" in f_data:
                    char["faction_affiliations"][f_key]["role"] = f_data["role"]
                if "value" in f_data:
                    char["faction_affiliations"][f_key]["value"] = clamp_int(f_data["value"], 0, 100, 0)
            continue

        # possessions (dict of dicts)
        if field == "possessions":
            if "possessions" not in char or not isinstance(char["possessions"], dict):
                char["possessions"] = {}
            for item, idata in value.items():
                if item not in char["possessions"]:
                    char["possessions"][item] = {"description": "", "value": 0}
                if "description" in idata:
                    char["possessions"][item]["description"] = idata["description"]
                if "value" in idata:
                    char["possessions"][item]["value"] = clamp_int(idata["value"], 0, 100, 0)
            continue

        # relationships (dict of dicts)
        if field == "relationships":
            if "relationships" not in char or not isinstance(char["relationships"], dict):
                char["relationships"] = {}
            for other, rdata in value.items():
                if other not in char["relationships"]:
                    char["relationships"][other] = {"description": "", "sentiment": 0}
                if "description" in rdata:
                    char["relationships"][other]["description"] += rdata["description"]
                if "sentiment" in rdata:
                    char["relationships"][other]["sentiment"] += clamp_int(rdata["sentiment"], 0, 100, 0)
            continue

        if field == "knowledge":
            if "knowledge" not in char or not isinstance(char["knowledge"], dict):
                char["knowledge"] = knowledge_template()
            for cat, data in value.items():
                # ===== CHARACTERS =====
                if cat == "characters":
                    for other_name, other_data in data.items():
                        if other_name not in char["knowledge"]["characters"]:
                            char["knowledge"]["characters"][other_name] = knowledge_character_entry_template()
                        target_char = char["knowledge"]["characters"][other_name]
                        # ---- BASICS ----
                        if "basics" in other_data:
                            for b_key, b_val in other_data["basics"].items():
                                if b_key not in target_char["basics"]:
                                    continue
                                if "value" in b_val:
                                    merge_confidence_value(
                                        target_char["basics"][b_key],
                                        b_val.get("value"),
                                        clamp_int(b_val.get("confidence", 0), 0, 100, 0)
                                    )
                                if "description" in b_val:
                                    merge_confidence_description(
                                        target_char["basics"][b_key],
                                        b_val.get("description"),
                                        clamp_int(b_val.get("confidence", 0), 0, 100, 0)
                                    )
                        # ---- GENERIC DICTS ----
                        for section in ["role", "traits", "background", "interests", "dislikes", "goals", "possessions"]:
                            if section in other_data:
                                if section not in target_char:
                                    target_char[section] = {}
                                for k, v in other_data[section].items():
                                    if k not in target_char[section]:
                                        target_char[section][k] = {"description": "", "confidence": 0}
                                    merge_confidence_description(
                                        target_char[section][k],
                                        v.get("description", ""),
                                        clamp_int(v.get("confidence", 0), 0, 100, 0)
                                    )
                        # ---- RELATIONSHIPS ----
                        if "relationships" in other_data:
                            for rel, rdata in other_data["relationships"].items():
                                if rel not in target_char["relationships"]:
                                    target_char["relationships"][rel] = {
                                        "description": "",
                                        "sentiment": 0,
                                        "confidence": 0
                                    }
                                if "description" in rdata:
                                    merge_confidence_description(
                                        target_char["relationships"][rel],
                                        rdata["description"],
                                        clamp_int(rdata.get("confidence", 0), 0, 100, 0)
                                    )
                                if "sentiment" in rdata:
                                    target_char["relationships"][rel]["sentiment"] = clamp_int(rdata["sentiment"], -100, 100, 0)
                        # ---- STATE ----
                        if "state" in other_data:
                            state = other_data["state"]
                            if "location" in state:
                                merge_confidence_value(
                                    target_char["state"]["location"],
                                    state["location"].get("value"),
                                    clamp_int(state["location"].get("confidence", 0), 0, 100, 0)
                                )
                            if "activity" in state:
                                merge_confidence_description(
                                    target_char["state"]["activity"],
                                    state["activity"].get("description"),
                                    clamp_int(state["activity"].get("confidence", 0), 0, 100, 0)
                                )
                            # PHYSICAL (observed)
                            if "physical" in state:
                                for p_key, pdata in state["physical"].items():
                                    if p_key not in target_char["state"]["physical"]:
                                        target_char["state"]["physical"][p_key] = {
                                            "description": "",
                                            "confidence": 0
                                        }
                                    merge_confidence_description(
                                        target_char["state"]["physical"][p_key],
                                        pdata.get("description", ""),
                                        clamp_int(pdata.get("confidence", 0), 0, 100, 0)
                                    )
                            # MENTAL (observed)
                            if "mental" in state:
                                for m_key, mdata in state["mental"].items():
                                    if m_key not in target_char["state"]["mental"]:
                                        target_char["state"]["mental"][m_key] = {
                                            "description": "",
                                            "confidence": 0
                                        }
                                    merge_confidence_description(
                                        target_char["state"]["mental"][m_key],
                                        mdata.get("description", ""),
                                        clamp_int(mdata.get("confidence", 0), 0, 100, 0)
                                    )
                        # ---- KNOWLEDGE BITS ----
                        if "knowledge_bits" in other_data:
                            for kb, kbdata in other_data["knowledge_bits"].items():
                                if kb not in target_char["knowledge_bits"]:
                                    target_char["knowledge_bits"][kb] = {
                                        "description": "",
                                        "confidence": 0,
                                        "decay": "medium"
                                    }
                                merge_confidence_description(
                                    target_char["knowledge_bits"][kb],
                                    kbdata.get("description", ""),
                                    clamp_int(kbdata.get("confidence", 0), 0, 100, 0)
                                )
                # ===== OTHER CATEGORIES (world / scene / hard) =====
                else:
                    if cat not in char["knowledge"]:
                        char["knowledge"][cat] = {}
                    deep_merge_dict(char["knowledge"][cat], data)
            continue

        if field == "memory":
            if "memory" not in char or not isinstance(char["memory"], dict):
                char["memory"] = {"recent": {}, "mid": {}}
            for mem_layer, mem_data in value.items():
                if mem_layer not in char["memory"]:
                    char["memory"][mem_layer] = {}
                for mem_key, mdata in mem_data.items():
                    if mem_key not in char["memory"][mem_layer]:
                        char["memory"][mem_layer][mem_key] = {
                            "description": "",
                            "impact": 0
                        }
                    if "description" in mdata:
                        char["memory"][mem_layer][mem_key]["description"] = mdata["description"]
                    if "impact" in mdata:
                        char["memory"][mem_layer][mem_key]["impact"] = clamp_int(mdata["impact"], 0, 100, 0)
            continue

        if field == "ongoing_processes":
            if "ongoing_processes" not in char or not isinstance(char["ongoing_processes"], dict):
                char["ongoing_processes"] = {}
            for p_key, pdata in value.items():
                if p_key not in char["ongoing_processes"]:
                    char["ongoing_processes"][p_key] = {
                        "description": "",
                        "progress": 0,
                        "priority": 0
                    }
                if "description" in pdata:
                    char["ongoing_processes"][p_key]["description"] = pdata["description"]
                if "progress" in pdata:
                    char["ongoing_processes"][p_key]["progress"] = clamp_int(pdata["progress"], 0, 100, 0)
                if "priority" in pdata:
                    char["ongoing_processes"][p_key]["priority"] = clamp_int(pdata["priority"], 0, 100, 0)
            continue

    # fallback: ignore unknown fields safely (log them for debugging)
    # grouping & generic information kind may need to be modified to be more specific/complex later
    # this way the format/content for input information is very high-quality demanded and highly specific, be careful
    # add removal mechanism
    # the adding and labeling of the key...repetitive?
    # the replacing/covering problem of each update...old information...?
    # the structure overall is not so clean

# !!! BETTER TO SEPARATE AND DIVIDE INTO DETAILED SECTORS WHEN UPDATING AND PROMPT DIFFERENTLY AND MORE DETAILY WHAT SHOULD BE UPDATED ACCORDING TO WHAT AND HOW.
# LONG-TERM TRAIT NOT UPDATED HERE (GOOD CALL). BUT THEY *SHOULD* BE UPDATED.
# BUT NOT AS IMMEDIATE-EFFECTS (LIKE THIS ONE), AS "DRIFTING".
# OR REACHING THE TIME/INTENSITY THRESHOLD.
def simplify_perception(perceived_events):
    scene = perceived_events.get("__scene__", {})
    result = {"events": []}
    if scene:  # only add if not empty
        result["scene"] = scene

    for eid, pdata in perceived_events.items():
        if eid == "__scene__":
            continue
        e = pdata.get("event", {})
        result["events"].append({
            "type": e.get("type", ""),
            "actor": e.get("actor", ""),
            "target": e.get("target", []),
            "content": e.get("content", ""),
            "confidence": pdata.get("confidence", 0)
        })
    return result

# FILTER...ONLY THE ALLOWED FIELDS GET UPDATED...
# INCOMPLETE HERE...
def filter_dict_fields(data, allowed_keys):
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in allowed_keys}
# allowed_top_fields = {
#     "location", "activity", "clothing",
#     "physical_state", "mental_state",
#     "possessions", "role",
#     "knowledge", "memory"
# }
# clean_changes = filter_dict_fields(changes, allowed_top_fields)
# merge_character_changes(chars, name, clean_changes)

def update_memory_from_perception(char_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    if char_name not in chars_all["characters"]:
        return

    simplified = simplify_perception(perceived_events)

    prompt = (
        "You are updating a character's MEMORY.\n\n"

        "MEMORY RULES:\n"
        "- Memory is subjective and narrative.\n"
        "- DO NOT include event IDs.\n"
        "- Summarize what happened in natural language.\n"
        "- Include emotional impact (0-100).\n"
        "- Only include significant events.\n"
        "- Do NOT infer personality or traits.\n"
        "- Do NOT invent unseen details.\n\n"

        "Return STRICT JSON:\n"
        "{\n"
        "  \"characters\": {\n"
        "    \"CHAR_NAME\": {\n"
        "      \"memory\": {\n"
        "        \"recent\": {\n"
        "          \"event_key\": {\n"
        "            \"description\": \"string\",\n"
        "            \"impact\": 0-100\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    payload = {
        "character_name": char_name,
        "perceived_events": simplified
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if "characters" in updates:
        merge_character_changes(chars_all, char_name, updates["characters"].get(char_name, {}))
        save_json(CHARACTERS_FILE, chars_all)

# make traits automatically emerge from knowledge_bits???
# !!! FOCO POINTS TO FIX HERE (THIS BLOC, TBH) !!!
def update_knowledge_characters(char_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    if char_name not in chars_all["characters"]:
        return

    simplified = simplify_perception(perceived_events)

    prompt = (
        "You are extracting NEW KNOWLEDGE about OTHER CHARACTERS.\n\n"

        "STRICT RULES:\n"
        "1. ONLY use perceived events.\n"
        "2. DO NOT use or assume prior knowledge.\n"
        "3. DO NOT infer personality or long-term traits.\n"
        "4. ALL outputs must be minimal and directly grounded.\n"
        "5. DO NOT overwrite or remove existing knowledge.\n"
        "6. DO NOT invent unseen facts.\n\n"

        "TRAITS:\n"
        "- Only short-term, observable traits (e.g., \"nervous\", \"aggressive\").\n"
        "- MUST be uncertain.\n"
        "- Confidence MUST be LOW (10-40).\n\n"

        "STATE:\n"
        "- Must reflect CURRENT observable state only.\n"
        "- Includes: location, activity, physical, mental.\n"
        "- No inference beyond what is visible.\n\n"

        "RELATIONSHIPS:\n"
        "- ONLY include if there is clear, direct interaction evidence.\n"
        "- DO NOT assume friendship, hostility, or roles.\n"
        "- Description must describe the observed interaction only. BE SHORT AND PRECISE.\n"
        "- Sentiment MUST be weak (-30 to 30).\n"
        "- Confidence MUST be LOW (10-40).\n\n"

        "POSSESSIONS:\n"
        "- ONLY update if explicitly gained, received, or taken.\n"
        "- DO NOT assume ownership.\n\n"

        "KNOWLEDGE_BITS:\n"
        "- Small, specific observations about the character.\n"
        "- Must be concrete (e.g., \"carrying a knife\", \"speaks softly\").\n"
        "- MUST NOT duplicate traits or state.\n"
        "- Confidence MUST be LOW (10-40).\n"
        "- Use short descriptions.\n\n"

        "Return STRICT JSON (no extra text):\n"
        "{\n"
        "  \"characters\": {\n"
        f"    \"{char_name}\": {{\n"
        "      \"knowledge\": {\n"
        "        \"characters\": {\n"
        "          \"OtherCharacter\": {\n"
        "            \"traits\": {\n"
        "              \"trait_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "            },\n"
        "            \"possessions\": {\n"
        "              \"item_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "            },\n"
        "            \"relationships\": {\n"
        "              \"OtherCharacter\": {\n"
        "                \"description\": \"string\",\n"
        "                \"sentiment\": 0,\n"
        "                \"confidence\": 0\n"
        "              }\n"
        "            },\n"
        "            \"state\": {\n"
        "              \"location\": {\"value\": \"string\", \"confidence\": 0},\n"
        "              \"activity\": {\"description\": \"string\", \"confidence\": 0},\n"
        "              \"physical\": {\n"
        "                \"aspect_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "              },\n"
        "              \"mental\": {\n"
        "                \"aspect_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "              }\n"
        "            },\n"
        "            \"knowledge_bits\": {\n"
        "              \"key\": {\n"
        "                \"description\": \"string\",\n"
        "                \"confidence\": 0,\n"
        "                \"decay\": \"slow|medium|fast\"\n"
        "              }\n"
        "            }\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )

    payload = {
        "character_name": char_name,
        "perceived_events": simplified
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if "characters" in updates:
        merge_character_changes(chars_all, char_name, updates["characters"].get(char_name, {}))
        save_json(CHARACTERS_FILE, chars_all)

# WAIT. WAIT. ONLY IN-SCENE CHARACTERS...NO??? OR I ALREADY FILTERED IT??? BY PERCEPTION??? WELL. PROBABLY (...)
# CHECK.
def update_knowledge_scene(char_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    if char_name not in chars_all["characters"]:
        return

    simplified = simplify_perception(perceived_events)

    prompt = (
        "You are extracting NEW KNOWLEDGE about the CURRENT SCENE.\n\n"

        "STRICT RULES:\n"
        "1. ONLY use perceived events and provided scene basics.\n"
        "2. DO NOT assume or infer hidden structure.\n"
        "3. ONLY include observable elements.\n"
        "4. ALL entries must include confidence (10-100).\n"
        "5. Use LOW confidence (10-40) for uncertain observations.\n"
        "6. DO NOT overwrite the entire scene.\n"
        "7. Keep outputs minimal and precise.\n\n"

        "YOU MAY UPDATE:\n"
        "- location\n"
        "- time (rough)\n"
        "- environment\n"
        "- rules\n"
        "- characters_present\n"
        "- objects\n"
        "- conflicts (only if clearly hostile interaction)\n"
        "- events (only if significant)\n\n"

        "Return STRICT JSON (no extra text):\n"
        "{\n"
        "  \"characters\": {\n"
        f"    \"{char_name}\": {{\n"
        "      \"knowledge\": {\n"
        "        \"scene\": {\n"
        "          \"location\": {\"description\": \"string\", \"confidence\": 0},\n"
        "          \"time\": {\"description\": \"string\", \"confidence\": 0},\n"
        "          \"environment\": {\n"
        "            \"aspect_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "          },\n"
        "          \"rules\": {\n"
        "            \"rule_key\": {\"description\": \"string\", \"severity\": 0, \"confidence\": 0}\n"
        "          },\n"
        "          \"characters_present\": {\n"
        "            \"CharacterName\": {\"focus\": 0}\n"
        "          },\n"
        "          \"objects\": {\n"
        "            \"object_key\": {\"description\": \"string\", \"confidence\": 0}\n"
        "          },\n"
        "          \"conflicts\": {\n"
        "            \"conflict_key\": {\"description\": \"string\", \"intensity\": 0, \"confidence\": 0}\n"
        "          },\n"
        "          \"events\": {\n"
        "            \"event_key\": {\"description\": \"string\", \"impact\": 0, \"confidence\": 0}\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )

    payload = {
        "character_name": char_name,
        "perceived_events": simplified
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if "characters" in updates:
        merge_character_changes(chars_all, char_name, updates["characters"].get(char_name, {}))
        
        char = chars_all["characters"][char_name]
        scene_knowledge = char["knowledge"].get("scene", {})
        conflicts = scene_knowledge.get("conflicts", {})
        scene_knowledge["dynamics"] = compute_scene_dynamics(conflicts)

        save_json(CHARACTERS_FILE, chars_all)

def update_self_state_from_perception(char_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    if char_name not in chars_all["characters"]:
        return

    simplified = simplify_perception(perceived_events)

    prompt = (
        "You are updating the CHARACTER'S OWN STATE.\n\n"

        "STRICT RULES:\n"
        "1. ONLY update immediate, observable state.\n"
        "2. You MAY update:\n"
        "   - location\n"
        "   - activity\n"
        "   - clothing\n"
        "   - physical_state\n"
        "   - mental_state\n\n"

        "3. POSSESSIONS:\n"
        "   - ONLY update if explicitly gained, received, or taken.\n"
        "   - DO NOT assume ownership.\n\n"

        "4. ROLE:\n"
        "   - ONLY update if explicitly assigned or promoted.\n\n"

        "5. NICKNAMES:\n"
        "   - ONLY update if explicitly used by another character.\n\n"

        "6. RELATIONSHIPS:\n"
        "- ONLY include if there is clear, direct interaction evidence.\n"
        "- DO NOT assume friendship, hostility, or roles.\n"
        "- Description must describe the observed interaction only.\n"
        "- Sentiment MUST be weak (-30 to 30).\n"

        "6. ALL values must be grounded in perceived events.\n"
        "7. DO NOT invent information.\n\n"

        "Return STRICT JSON (no extra text):\n"
        "{\n"
        "  \"characters\": {\n"
        f"    \"{char_name}\": {{\n"
        "      \"location\": \"string\",\n"
        "      \"activity\": \"string\",\n"
        "      \"clothing\": \"string\",\n"
        "      \"relationships\": {\n"
        "        \"CharacterName\": {\n"
        "          \"description\": \"string\",\n"
        "          \"sentiment\": 0\n"
        "        }\n"
        "      },\n"
        "      \"physical_state\": {\n"
        "        \"aspect_key\": {\"description\": \"string\", \"value\": 0}\n"
        "      },\n"
        "      \"mental_state\": {\n"
        "        \"emotion_key\": {\"description\": \"string\", \"value\": 0}\n"
        "      },\n"
        "      \"possessions\": {\n"
        "        \"item_key\": {\"description\": \"string\", \"value\": 0}\n"
        "      },\n"
        "      \"role\": {\n"
        "        \"role_key\": {\"description\": \"string\", \"value\": 0}\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )

    payload = {
        "character_name": char_name,
        "perceived_events": simplified
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if "characters" in updates:
        merge_character_changes(chars_all, char_name, updates["characters"].get(char_name, {}))
        save_json(CHARACTERS_FILE, chars_all)

def update_character_from_perception(char_name, perceived_events):
    update_memory_from_perception(char_name, perceived_events)
    update_knowledge_characters(char_name, perceived_events)
    update_knowledge_scene(char_name, perceived_events)
    update_self_state_from_perception(char_name, perceived_events)

# DECAY MECHANISM
DECAY_RATES = {
    "fast": 0.7,
    "medium": 0.85,
    "slow": 0.95
}
def decay_knowledge(character, hours_passed):
    for other, data in character["knowledge"]["characters"].items():
        for kb_key, kb in data.get("knowledge_bits", {}).items():
            rate = DECAY_RATES.get(kb.get("decay", "medium"), 0.85)
            for _ in range(int(hours_passed)):
                kb["confidence"] = int(kb["confidence"] * rate)

            if kb["confidence"] < 5:
                del data["knowledge_bits"][kb_key]

def decay_memory(character, hours_passed):
    for layer in ["recent"]:
        for key, mem in list(character["memory"][layer].items()):
            mem["impact"] = int(mem["impact"] * 0.9)

            if mem["impact"] < 5:
                del character["memory"][layer][key]


# =========================
# PLAYER ACTION RELATED
# =========================
def create_character_from_description(name, description_text):
    """
    Create or heavily initialize a character sheet from a natural-language description.
    """
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

    template = character_template()

    if name not in chars["characters"]:
        chars["characters"][name] = copy.deepcopy(template)

    prompt = (
        "You are a character-creation assistant.\n"
        "Given paragraphs describing characters, fill out as much of this character sheet as possible.\n"
        "Only include fields you can infer; omit unknowns.\n"
        "Use integers on a 0–100 scale for all strength/impact/value fields.\n"
        "Return STRICT JSON with this schema:\n\n"
        +character_information_extract_prompt()+
        "\n\nOnly include characters that are detected from the paragraph.\n"
        "If nothing is detected, return {\"characters\": {}}.\n"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": description_text}
        ]
    )

    content = response.choices[0].message["content"]
    try:
        updates = json.loads(content)
    except json.JSONDecodeError:
        return

    merge_character_changes(chars, name, updates)

    save_json(CHARACTERS_FILE, chars)

def detect_and_create_character_from_input(player_action):
    """
    Detect whether the player's input describes a character.
    If so, extract the name + description and create/update the character sheet.
    """

    detection_prompt = (
        "You are an assistant that detects whether a text describes a character.\n"
        "If the text describes a character, return STRICT JSON:\n"
        "{ \"name\": \"Character Name\", \"description\": \"Full description\" }\n"
        "If it does NOT describe a character, return {}.\n"
        "A character description may include appearance, personality, background, roles, or abilities.\n"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": detection_prompt},
            {"role": "user", "content": player_action}
        ]
    )

    content = response.choices[0].message["content"]

    try:
        data = json.loads(content)
    except:
        return  # invalid JSON, ignore

    if not isinstance(data, dict):
        return

    if "name" in data and "description" in data:
        create_character_from_description(data["name"], data["description"])
    
# =========================
# GROQ CALL: SCENE UPDATES
# =========================
def scene_template():
    return {
        "location": {
            "key": "",
            "name": "",
            "description": ""
        },

        "time": {
            "time_of_day": "",
            "elapsed_hours": 0.0
        },

        "characters_present": {},   # name -> {"focus": all 100 for now}
        # like engagement...etc. right.
        "objects": {},              # can add position keys later. for them.
        # state based (owner, etc)

        "environment": {
            "weather": {"description": "", "severity": 0},
            # maybe more like "volcano erupting"...? for later, anyway.
            # spacial things here too...later. like what at where (positions).
            # overlap with the above...? anyway.
        },

        "rules": {},    # constraints, etc. with description and severity as values
        # like, keep silent or die?

        "dynamics": {
            "danger_level": 0,
            "tension": 0
        },

        "conflicts": {},            # conflict_key -> {...}
        # with descriptions, parties, intensity, status        
        "events": {}                # event_key -> {...}
        # short-lived, high-impact scene happenings
        # lifecycles. important.
    }

def classify_speech_intent(event):
    prompt = (
        "Classify the intent of this speech.\n"
        "ONLY use the categories provided.\n"
        "DO NOT invent new category.\n"
        "Return STRICT JSON:\n"
        "{ \"intent\": \"hostile|neutral|friendly\", \"intensity\": 0-100 }\n"
    )

    payload = {
        "actor": event["actor"],
        "target": event.get("target", []),
        "content": event.get("content", "")
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )

    try:
        return json.loads(response.choices[0].message["content"])
    except:
        return {"intent": "neutral", "intensity": 0}

def get_conflict_key(a, b):
    return "|".join(sorted([a, b]))

def update_conflict(scene, a, b, delta_intensity, current_time):
    if "conflicts" not in scene:
        scene["conflicts"] = {}

    key = get_conflict_key(a, b)

    if key not in scene["conflicts"]:
        scene["conflicts"][key] = {
            "parties": {a: 50, b: 50},
            "intensity": 0,
            "status": "active",
            "last_updated": current_time
        }

    conflict = scene["conflicts"][key]
    MAX_DELTA_PER_ROUND = 20
    conflict["intensity"] = clamp_int(conflict["intensity"] + min(delta_intensity, MAX_DELTA_PER_ROUND), 0, 100, 0)
    conflict["status"] = "active"
    conflict["last_updated"] = current_time

    # BUT HOW ABOUT DESCRIPTIONS??? AND THE DIFFERENCE BETWEEN QUARRELS AND FIGHTS???

def handle_speech_event(event, scene, current_time):
    result = classify_speech_intent(event)

    intent = result.get("intent", "neutral")
    intensity = clamp_int(result.get("intensity", 0), 0, 100, 0)

    if intent != "hostile":
        return

    actor = event["actor"]
    targets = event.get("target", [])

    for t in targets:
        update_conflict(scene, actor, t, intensity, current_time)

def extract_action_effects(event):
    prompt = (
        "Extract physical effects of this action.\n"
        "ONLY extract what's obvious. DO NOT infer implications.\n"
        "ONLY use the categories provided (if provided). DO NOT invent new ones.\n"
        "Return STRICT JSON:\n"
        "{\n"
        "  \"object_changes\": [\n"
        "    {\n"
        "      \"object\": \"string\",\n"
        "      \"change\": \"picked_up|dropped|damaged|moved\",\n"
        "      \"new_owner\": \"string or null\"\n"
        "    }\n"
        "  ],\n"
        "  \"environment_changes\": [\n"
        "    {\n"
        "      \"key\": \"string\",\n"
        "      \"description\": \"string\",\n"
        "      \"severity\": 0-100\n"
        "    }\n"
        "  ]\n"
        "  \"interaction\": [\n"
        "    {\n"
        "      \"type\": \"none|hostile|friendly\",\n"
        "      \"targets\": [\"string\"],\n"
        "      \"intensity\": 0-100\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )
    payload = {
        "actor": event["actor"],
        "content": event.get("content", "")
    }
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )
    try:
        return json.loads(response.choices[0].message["content"])
    except:
        return {"object_changes": [], "environment_changes": []}

def apply_object_changes(scene, event, changes):
    if "objects" not in scene:
        scene["objects"] = {}

    actor = event["actor"]

    for c in changes:
        obj = c.get("object")
        change = c.get("change")
        new_owner = c.get("new_owner")

        if not obj:
            continue

        if obj not in scene["objects"]:
            scene["objects"][obj] = {
                "name": obj,
                "state": "",
                "owner": None
            }
        o = scene["objects"][obj]
        if change == "picked_up":
            o["owner"] = new_owner or actor
        elif change == "dropped":
            o["owner"] = None
        elif change == "damaged":
            o["state"] = "damaged"

def apply_environment_changes(scene, changes):
    if "environment" not in scene:
        scene["environment"] = {}

    for c in changes:
        key = c.get("key")
        if not key:
            continue

        scene["environment"][key] = {
            "description": c.get("description", ""),
            "severity": clamp_int(c.get("severity", 0), 0, 100, 0)
        }

def classify_movement(event):
    prompt = (
        "Determine if this action involves the actor leaving the current scene.\n"
        "Be conservative: ONLY return 'exit' if the action clearly indicates leaving the scene.\n"
        "Otherwise return 'none'.\n\n"
        "Return STRICT JSON:\n"
        "{ \"movement\": \"exit|none\" }\n"
    )
    payload = {
        "actor": event["actor"],
        "content": event.get("content", "")
    }
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload)}
        ]
    )
    try:
        return json.loads(response.choices[0].message["content"])
    except:
        return {"movement": "none"}

def remove_character_from_scene(scene, char_name):
    if "characters_present" in scene:
        scene["characters_present"].pop(char_name, None)

def handle_action_event(event, scene, current_time):
    result = extract_action_effects(event)

    apply_object_changes(scene, event, result.get("object_changes", []))
    apply_environment_changes(scene, result.get("environment_changes", []))

    interaction = result.get("interaction", {})
    if interaction.get("type") == "hostile":
        for t in interaction.get("targets", []):
            update_conflict(
                scene,
                event["actor"],
                t,
                interaction.get("intensity", 0),
                current_time
            )
    movement = classify_movement(event)
    if movement.get("movement") == "exit":
        remove_character_from_scene(scene, event["actor"])      

def log_scene_event(event, scene, current_time):
    if "events" not in scene:
        scene["events"] = {}
    eid = event["id"]
    scene["events"][eid] = {
        "type": event["type"],
        "actor": event["actor"],
        "target": event.get("target", []),
        "content": event.get("content", ""),
        "intensity": event.get("metadata", {}).get("intensity", 0),
        "timestamp": current_time
    }

def process_single_event(event, scene, current_time):
    etype = event.get("type")
    if etype == "thought":
        return  # no scene impact
    # Always log the event first
    log_scene_event(event, scene, current_time)
    if etype == "speech":
        handle_speech_event(event, scene, current_time)
    elif etype == "action":
        handle_action_event(event, scene, current_time)

def update_scene_dynamics(scene):
    conflicts = scene.get("conflicts", {})
    if not conflicts:
        scene["dynamics"]["tension"] = 0
        return
    total = sum(c["intensity"] for c in conflicts.values())
    avg = total / len(conflicts)
    scene["dynamics"]["tension"] = int(avg)
    scene["dynamics"]["danger_level"] = int(avg * 0.8)

def decay_conflicts(scene, current_time):
    for key, c in list(scene.get("conflicts", {}).items()):
        dt = current_time - c.get("last_updated", current_time)
        decay_factor = 0.9 ** dt
        c["intensity"] = int(c["intensity"] * decay_factor)
        if c["intensity"] < 5:
            c["status"] = "resolved"

def prune_old_events(scene, current_time, max_age=5):
    for eid, e in list(scene.get("events", {}).items()):
        if current_time - e.get("timestamp", current_time) > max_age:
            scene["events"].pop(eid, None)

def process_events_into_scene(events, scene, current_time):
    """
    Main entry: apply a batch of events to the scene.
    """
    for event in events:
        process_single_event(event, scene, current_time)

    # After all events
    update_scene_dynamics(scene)
    decay_conflicts(scene, current_time)
    prune_old_events(scene, current_time)

    return scene

# =========================
# WORLD SECT - FOR NOW
# =========================
def world_template():
    return {
        "setting": "",
        "rules": {},

        "factions": {
            # faction_key: {...}
        },

        "cultures": {},

        "important_places": {
            # place_key: {...}
        },

        "important_events": {
            # event_key: {...}
        }
    }

def faction_template():
    return {
        "name": "",
        "description": "",
        "rank": "",
        "type": "",
        "ideology": "",
        "goals": {},
        "influence": 0,

        "resources": {},

        "territory": {
            # place_key: {"control": 0-100}
        },

        "leaders": {
            # character_name: {"role": "", "influence": 0}
        },

        "relationships": {
            # other_faction_key: -100 to 100
        }
    }

def place_template():
    return {
        "name": "",
        "description": "",
        "atmosphere": {
            "description": "",
            "value": 0
        },

        "faction_control": {
            # faction_key: {"control": 0-100}
        },

        "danger_level": 0,
        "importance": 0,

        "risk_profile": {
            "natural": {},
            "magical": {},
            "political": {}
        }
    }

def event_template():
    return {
        "description": "",
        "location": "",
        "factions_involved": {},
        "characters_involved": {},
        "impact": 0,
        "type": "",
        "status": "ongoing"  # <-- critical for later cleanup
    }

# INITIALIZE WORLD KNOWLEDGE FOR CHARACTERS - FOR NOW
# Source mechanisms??? -> Network/Propagation/...(FOR LATER)
def build_initial_world_knowledge(world, scene):
    knowledge = {
        "setting": {
            "summary": world.get("setting", ""),
            "confidence": 100
        },
        "rules": {},
        "factions": {},
        "cultures": {},
        "places": {},
        "events": {}
    }
    MAX_ITEMS = 5

    # --- RULES (all, high confidence) ---
    for k, r in world.get("rules", {}).items():
        knowledge["rules"][k] = {
            "description": r.get("description", ""),
            "severity": r.get("severity", 0),
            "confidence": 100
        }

    # --- CURRENT LOCATION (highest priority) ---
    current_place = scene["location"]["key"]
    places = world.get("important_places", {})
    if current_place in places:
        p = places[current_place]
        knowledge["places"][current_place] = {
            "name": p["name"],
            "description": p["description"],
            "confidence": 100   # direct presence
        }

    # --- OTHER PLACES (medium confidence) ---
    for k, p in list(places.items()):
        if k not in knowledge["places"]:
            knowledge["places"][k] = {
                "name": p["name"],
                "description": p["description"],
                "confidence": 60
            }
        if len(knowledge["places"]) >= MAX_ITEMS:
            break

    # --- FACTIONS (by influence) ---
    factions = sorted(
        world.get("factions", {}).items(),
        key=lambda x: x[1].get("influence", 0),
        reverse=True
    )
    for k, f in factions[:MAX_ITEMS]:
        knowledge["factions"][k] = {
            "name": f["name"],
            "description": f["description"],
            "confidence": 70
        }

    # --- EVENTS (by impact) ---
    events = sorted(
        world.get("important_events", {}).items(),
        key=lambda x: x[1].get("impact", 0),
        reverse=True
    )
    for k, e in events[:MAX_ITEMS]:
        knowledge["events"][k] = {
            "description": e["description"],
            "importance": e.get("impact", 0),
            "confidence": 50
        }
    return knowledge

# METADATE STORAGE??? FOR EACH FILE??? NEEDED???
def initialize_characters_with_world_knowledge():
    chars_data = load_json(CHARACTERS_FILE, {"characters": {}})
    world = load_json(WORLD_BIBLE_FILE, world_template())
    scene = load_json(SCENE_STATE_FILE, scene_template())
    characters = chars_data.get("characters", {})

    updated = False
    for char_key, char_data in characters.items():
        # If no knowledge OR empty → initialize
        if "knowledge" not in char_data or not char_data["knowledge"]:
            char_data["knowledge"] = knowledge_template()

            # Build world knowledge
            world_knowledge = build_initial_world_knowledge(world, scene)

            # Inject
            char_data["knowledge"]["world"] = world_knowledge

            updated = True

    if updated:
        save_json(CHARACTERS_FILE, chars_data)

# =========================
# INITIALIZING GAME STATE
# =========================
def game_round_template():
    return {
        "current_round": 0,
        "current_phase": "",
        "current_phase_step": "",
        "players_with_death_counts": [],
        "eliminated_players": [],
        "eliminated_roles": [],
        "game_status": "ongoing"  # or "completed"
    }

def game_rule():
    return {
        "Werewolves_Table": {
            "description": (
                "Game setup: 14 players are assigned the roles of 4 werewolves, 5 villagers, 1 seer, 1 witch, 1 hunter, 1 knight, and 1 guardian angel.\n"
                "Each player receives one role.\n"
                "Werewolves are on Team Werewolf; all other roles are on Team Village.\n"
                "Win conditions:\n"
                "- Werewolves win if all Village players are dead.\n"
                "- Village wins if all Werewolves are dead.\n"
                "- If all players are dead, the game ends in a tie.\n\n"
            
                "All players strictly follow these rules:\n"
                "No players know the roles of other players at the start of the game.\n"
                "Except for werewolves, no players can reveal roles to others in a truly reliable or fully believable way.\n"
                "Game phases:\n"
                "- The game starts with the night phase.\n"
                "- Night phase action order: 1. seer, 2. werewolves, 3. guardian angel, 4. witch, 5. hunter (if triggered).\n"
                "- Day phase: two rounds of open discussion, then voting.\n\n"

                "General rules:\n"
                "- All actions and votes must target living players unless explicitly stated otherwise.\n"
                "- Dead players cannot act, speak, or be targeted.\n\n"

                "Night rules:\n"
                "- All players cannot perceive, speak, or act.\n"
                "- Then player(s) with the corresponding role(s) executes the following actions in order.\n"
                "- After each action, the player(s) resumes the inactive state:\n"
                "1. Seer:\n"
                "   - May choose to inspect one living player.\n"
                "   - Learns only the target's team (Werewolf or Village), not role.\n"
                "2. Werewolves:\n"
                "   - See the roles of other players who are also werewolves.\n"
                "   - Hold three rounds of private discussion.\n"
                "   - Then vote once to select a target to kill.\n"
                "   - The player with the most votes is selected.\n"
                "   - If there is a tie, no one is targeted.\n"
                "   - May choose no target or target themselves.\n"
                "3. Guardian Angel:\n"
                "   - May choose to protect one living player.\n"
                "   - Cannot protect the same player on consecutive nights.\n"
                "   - Protection can only invalidate werewolves' targeting.\n"
                "   - If the protected player is not targeted, the protection is wasted.\n"
                "4. Witch:\n"
                "   - Has one save potion and one poison potion, each usable once per game.\n"
                "   - Is informed of the current werewolf target result AFTER guardian angel's protection decision.\n"
                "   - May choose to use the save potion to cancel the targeting.\n"
                "   - If no player is targeted, the save step is skipped.\n"
                "   - May then choose to use poison potion to poison one living player.\n"
                "5. Hunter:\n"
                "   - Triggers ONLY if still targeted by werewolves after guardian angel's and witch's actions.\n"
                "   - May choose to shoot one living player.\n"
                "   - After shooting, is still targeted by werewolves.\n"
                "Night resolution:\n"
                "- Death resolution order:\n"
                "  1. Werewolf target (if still valid after guardian angel's and witch's actions)\n"
                "  2. Witch poison (if the witch chooses to use it)\n"
                "  3. Hunter shot (if triggered)\n"
                "- All deaths are applied together at the end of the night.\n\n"

                "Day rules:\n"
                "- Day begins with announcement of all deaths (players' names only, no roles or causes).\n"
                "- Dead players cannot speak, act or participate in any way.\n"
                "- Two rounds of open discussion regarding which player to eliminate (lynch), the order of speech is randomized.\n"
                "- All players can see and hear each other clearly.\n"
                "- Interrupt actions during discussion:\n"
                "- In their turn to speak:\n"
                "  - Knight (once per game):\n"
                "    * May choose to challenge one living player.\n"
                "    * If target is a werewolf, target dies.\n"
                "    * Otherwise, the knight and the target both die.\n"
                "    * Discussion ends immediately after resolution.\n"
                "    * No vote occurs.\n"
                "    * Proceed to next night.\n"
                "  - Werewolf:\n"
                "    * A werewolf may choose to reveal themselves.\n"
                "    * The werewolf dies immediately.\n"
                "    * Discussion ends immediately.\n"
                "    * No vote occurs.\n"
                "    * Proceed to next night.\n"
                "- An interrupt action is applied and resolved immediately upon declaration, which means only the first declared action will be applied.\n"
                "- If no interrupting actions occur, voting occurs after discussion:\n"
                "  - All living players vote once.\n"
                "  - Each living player has one vote.\n"
                "  - Each player votes for a living player to eliminate; can vote themselves, can abstain.\n"
                "  - The player with the most votes is eliminated.\n"
                "  - If there is a tie, no one is eliminated.\n"
                "  - Then proceed to next night.\n\n"

                "- The game alternates between night and day phases until a win condition is met.\n"
                "- Win conditions are checked at the end of each phase.\n\n"

                "- Team werewolf's objective is to eliminate all village players.\n"
                "- Team village's objective is to eliminate all werewolves."
            ),

            "severity": 100
        }
    }

def initialize_game_state():
    scene = scene_template()
    world = world_template()
    game_rounds = game_round_template()

    # ---- Fill scene ----
    scene["location"] = {
        "key": "table_werewolves",
        "name": "table",
        "description": "A large round table where all players gather for Werewolves Table game."
    }
    scene["time"] = {
        "time_of_day": "morning",
        "elapsed_hours": 0.0
    }
    scene["environment"] = {
        "table": {
            "description": "All players are seated around a large round table, clearly seeing and hearing each other. The entire game takes place at this table with no movement or spatial separation.",
            "severity": 100
        }
    }
    scene["rules"] = game_rule()

    # ---- World ----
    world["setting"] = "A fully abstract social deduction game taking place around a single table. No physical movement or environmental complexity exists."
    world["rules"] = game_rule()

    save_json(SCENE_STATE_FILE, scene)
    save_json(WORLD_BIBLE_FILE, world)
    save_json(GAME_ROUNDS_FILE, game_rounds)

# =========================
# INITIALIZING CHARACTERS
# =========================
def get_team(role):
    return "werewolf" if role == "werewolf" else "village"

def get_ability(role):
    return {
        "werewolf": {"kill_at_night": True},
        "villager": {},
        "seer": {"inspect_at_night": True},
        "witch": {"save_potion": 1, "poison_potion": 1},
        "hunter": {"shoot_at_night_if_killed_by_werewolf": True},
        "knight": {"challenge_chance": 1},
        "guardian_angel": {"last_protected": None}
    }.get(role, {})

def generate_personality_with_llm():
    prompt = (
        "Generate a personality profile for a character in a social deduction game.\n\n"
        "Rules:\n"
        "- Keep it SHORT\n"
        "- No backstory\n"
        "- Focus on behavior in discussion and decision-making\n\n"
        "Return STRICT JSON:\n"
        "{\n"
        "  \"personality\": {\n"
        "    \"trait_key\": {\n"
        "      \"description\": \"string\",\n"
        "      \"value\": 0-100\n"
        "    }\n"
        "  }\n"
        "}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "generate personality for the character"}
            ]
        )
        content = response.choices[0].message["content"]
        data = json.loads(content)
        return data.get("personality", {})
    except:
        return {}

def generate_appearance_with_llm(gender, age_apparent):
    prompt = (
        "Generate a brief appearance description for a " + gender + " character that is " + str(age_apparent) + " years old.\n\n"
        "Rules:\n"
        "- Keep it VERY SHORT (1-2 sentences)\n"
        "- Focus on distinctive features that can be easily perceived at the table\n\n"
        "Return STRICT JSON:\n"
        "{\n"
        "  \"appearance\": {\n"
        "    \"trait_key\": {\n"
        "      \"description\": \"string\",\n"
        "      \"value\": 0-100\n"
        "    }\n"
        "  }\n"
        "}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "generate appearance for the character"}
            ]
        )
        content = response.choices[0].message["content"]
        data = json.loads(content)
        return data.get("appearance", {})
    except:
        return {}

def initialize_characters(CHARACTER_NAMES):
    chars = {"characters": {}}

    # ---- role pool ----
    roles = (
        ["werewolf"]*4 +
        ["villager"]*5 +
        ["seer"] +
        ["witch"] +
        ["hunter"] +
        ["knight"] +
        ["guardian_angel"]
    )
    random.shuffle(roles)

    for name, role in zip(CHARACTER_NAMES, roles):
        char = character_template()

        # ---- basics ----
        char["gender"] = random.choice(["male", "female"])
        char["age_apparent"] = random.randint(18, 26)
        char["age_actual"] = char["age_apparent"] + random.randint(0, 3)
        char["species"] = "human"

        # ---- appearance via LLM----
        char["appearance"] = generate_appearance_with_llm(char["gender"], char["age_apparent"])

        # ---- personality via LLM ----
        personality = generate_personality_with_llm()
        if personality:
            char["personality"] = personality
        
        # ---- goal ----
        char["goals"] = {"win_the_game": {"description": "win the game for their team", "value": 100}}

        # ---- ongoing process ----
        char["ongoing_processes"] = {"playing_the_game": {"description": "playing the game and aiming to win", "value": 100}}

        # ---- mental state ----
        char["mental_state"] = {"calmness": {"description": "the clarity of thought", "value": 70}}

        # ---- location / activity ----
        char["location"] = "table"
        char["activity"] = "sitting at the table"

        # ---- game status ----
        char["game_status"] = {
            "role": role,
            "team": get_team(role),
            "ability": get_ability(role),
            "death_count": {},
            "is_dead": False
        }

        chars["characters"][name] = char

    save_json(CHARACTERS_FILE, chars)

def summarize_appearance_with_llm(appearance_data):
    prompt = (
        "Summarize the following appearance traits into a concise description that can be easily perceived.\n\n"
        "Rules:\n"
        "- Focus on distinctive features\n"
        "- Keep it VERY SHORT (1-2 sentences)\n\n"
        "Return a string."
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(appearance_data)}
            ]
        )
        content = response.choices[0].message["content"]
        return content
    except:
        return ""

def initialize_characters_scene_world():
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    scene = load_json(SCENE_STATE_FILE, scene_template())
    world = load_json(WORLD_BIBLE_FILE, world_template())

    for name, char in chars.get("characters", {}).items():
        scene["characters_present"][name] = {"focus": 100}
        char["knowledge"]["scene"]["location"] = {
            "name": scene["location"]["name"],
            "description": scene["location"]["description"],
            "confidence": 100
        },
        char["knowledge"]["scene"]["time"] = {
            "time_of_day": scene["time"]["time_of_day"],
            "elapsed_hours": scene["time"]["elapsed_hours"],
            "confidence": 100
        },
        char["knowledge"]["scene"]["environment"] = {
            "table": {
                "description": scene["environment"]["table"]["description"],
                "severity": scene["environment"]["table"]["severity"],
                "confidence": 100
            }
        }
        char["knowledge"]["scene"]["rules"] = {
            "Werewolves_Table": {
                "description": scene["rules"]["Werewolves_Table"]["description"],
                "severity": 100,
                "confidence": 100
            }
        }
        char["knowledge"]["world"]["setting"] = {
            "table": {
                "description": world["setting"],
                "confidence": 100
            }
        }
        char["knowledge"]["world"]["rules"] = {
            "Werewolves_Table": {
                "description": "same as the scene rules",
                "confidence": 100
            }
        }
        char["memory"]["recent"] = {"game_start": {"description": "the game has started", "impact": 100}}
    
    for name, char in chars.get("characters", {}).items():
        char["knowledge"]["scene"]["characters_present"] = scene["characters_present"]
        for others, char_others in scene["characters_present"].items():
            if others != name:
                char["knowledge"]["characters"][others] = knowledge_character_entry_template()
                char["knowledge"]["characters"][others]["basics"]["gender"] = {"value": chars["characters"][others].get("gender"), "confidence": 100}
                char["knowledge"]["characters"][others]["basics"]["age_apparent"] = {"value": chars["characters"][others].get("age_apparent"), "confidence": 90}
                char["knowledge"]["characters"][others]["basics"]["appearance"] = {"description": summarize_appearance_with_llm(chars["characters"][others].get("appearance", {})), "confidence": 90}
                char["knowledge"]["characters"][others]["goals"] = {"win_the_game": {"description": "win the game for their team", "value": 100, "confidence": 100}}
                char["knowledge"]["characters"][others]["state"]["location"] = {"value": "table", "confidence": 100}
                char["knowledge"]["characters"][others]["state"]["activity"] = {"description": "sitting at the table playing game", "confidence": 100}
                char["knowledge"]["characters"][others]["game_status"]["death_count"] = {"value": {}, "confidence": 100}
                char["knowledge"]["characters"][others]["game_status"]["is_dead"] = {"value": False, "confidence": 100}
                if char["game_status"]["team"] == "werewolf":
                    if chars["characters"][others]["game_status"]["team"] == "werewolf":
                        char["knowledge"]["characters"][others]["game_status"]["role"] = {"value": "werewolf", "confidence": 100}
    
    save_json(CHARACTERS_FILE, chars)
    save_json(SCENE_STATE_FILE, scene)

# =========================
# ACTIONS & SPEECHES & DECISIONS RELATED
# =========================
def build_llm_view(chars, actor_name):
    actor = chars["characters"][actor_name]

    send_data = {
        "name": actor_name,
        "gender": actor["gender"],
        "age_apparent": actor["age_apparent"],
        "age_actual": actor["age_actual"],
        "species": actor["species"],

        "appearance": actor["appearance"],
        "personality": actor["personality"],

        "goals": actor["goals"],
        "mental_state": actor["mental_state"],
        "ongoing_processes": actor["ongoing_processes"],

        "memory": actor.get("memory", {}),

        "knowledge": {
            "scene": actor["knowledge"]["scene"],
            "world": {
                "setting": actor["knowledge"]["world"]["setting"],
                "rules": actor["knowledge"]["world"]["rules"]
            },
            "characters": {}
        },

        "game_status": actor.get("game_status",{}),
        "relationships": actor.get("relationships", {}),
        "location": actor["location"],
        "activity": actor["activity"]
    }

    for name, target in chars["characters"].items():
        if name == actor_name:
            continue
        send_data["knowledge"]["characters"][name] = {
            "basics": {
                "gender": actor["knowledge"]["characters"][name]["basics"]["gender"],
                "age_apparent": actor["knowledge"]["characters"][name]["basics"]["age_apparent"],
                "appearance": actor["knowledge"]["characters"][name]["basics"]["appearance"],
            },

            "goals": actor["knowledge"]["characters"][name].get("goals", {}),
            "traits": actor["knowledge"]["characters"][name].get("traits", {}),

            "state": {
                "location": actor["knowledge"]["characters"][name]["state"]["location"],
                "activity": actor["knowledge"]["characters"][name]["state"]["activity"],
                "mental": actor["knowledge"]["characters"][name]["state"]["mental"]
            },

            "game_status": actor["knowledge"]["characters"][name]["game_status"],
            "relationships": actor["knowledge"]["characters"][name].get("relationships", {}),

            "knowledge_bits": actor["knowledge"]["characters"][name].get("knowledge_bits", {})
        }

    return send_data

# ------------------------
# HELPERS
# ------------------------
def get_alive_role(chars, role):
    for name, c in chars["characters"].items():
        if c["game_status"]["role"] == role and not c["game_status"]["is_dead"]:
            return name
    return None

def get_alive_roles(chars, role):
    return [
        name for name, c in chars["characters"].items()
        if c["game_status"]["role"] == role and not c["game_status"]["is_dead"]
    ]

def is_valid_target(name, chars):
    return name in chars["characters"] and not chars["characters"][name]["game_status"]["is_dead"]

def get_valid_targets(chars, exclude=None):
    if exclude is None:
        exclude = []
    return [
        name
        for name, char in chars["characters"].items()
        if not char["game_status"]["is_dead"] and name not in exclude
    ]
# -------------------------
# -------------------------

def ask_llm_for_target(actor_name, action_type, action_target):
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    game_round = load_json(GAME_ROUNDS_FILE, {})
    view = build_llm_view(chars, actor_name)

    if action_type == "seer":
        question = "You are the Seer. Which player do you want to inspect tonight?"

    elif action_type == "guardian_angel":
        question = "You are the Guardian Angel. Which player do you want to protect tonight? (reminder: you cannot protect the same player as last night)"

    elif action_type == "witch_save":
        question = f"You are the Witch. The player '{action_target}' is going to die tonight. Do you want to use your save potion?"

    elif action_type == "witch_poison":
        question = "You are the Witch. Which player do you want to poison tonight, or choose no one?"

    elif action_type == "hunter":
        question = "You are the Hunter. You are going to die tonight. Which player do you want to shoot?"

    else:
        return None

    SYSTEM_PROMPT = """
        You are simulating a character in a structured social deduction game.
        You will be asked a question and you must provide a reasonable answer given the information provided.

        Rules:
        - You MUST only use the information provided in the input.
        - You MUST NOT assume, invent, or hallucinate any information not present.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to reason and deduct.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 200 characters, any excess will be truncated.
        - Then provide a final answer to the question asked.
        - you MUST provide an answer within the given VALID range of selection, otherwise your answer will be considered as "no action".

        Return STRICT JSON in this format:
        {
        "reasoning": "",
        "answer": "",
        }
    """
    if action_type in ["seer", "witch_poison", "hunter"]:
        valid_range_of_selection = get_valid_targets(chars)
    elif action_type == "guardian_angel":
        valid_range_of_selection = get_valid_targets(chars, exclude=[view["game_status"]["ability"].get("last_protected")])
    else:
        valid_range_of_selection = ["yes", "no"]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({
                    "character_information": view,
                    "introduction": "This is the night phase, consider your answer and possible consequence carefully; every decision may decide which team wins the game.",
                    "question": question,
                    "VALID_range_of_selection": valid_range_of_selection
                })}
            ]
        )
        content = response.choices[0].message["content"]
        data = json.loads(content)

        # ---- use output ----
        mem_snippet = {
            "actor": actor_name,
            "action": f"answered '{data.get('answer')}' to the question '{question}'",
            "reasoning": data.get("reasoning", "")[:200],  # truncate if too long
            "result": "success" if data.get("answer") in valid_range_of_selection else "out of range, invalid - treated as no action"
        }
        current_round = game_round.get("current_round", 0)
        chars["characters"][actor_name]["memory"]["recent"][f"round_{current_round}_night_{action_type}"] = {"description": mem_snippet, "impact": 100}
        save_json(CHARACTERS_FILE, chars)

        answer = data.get("answer")
        return answer

    except Exception as e:
        print("LLM decision error:", e)
        return None
# IF LLM'S ANSWER'S *NOT* "PRECISELY" *THAT*, WILL BE ISSUES. NEED MORE LLM OUTPUT ERROR TOLERANCE HERE.

def ask_llm_for_target_wolves(wolves):
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    game_round = load_json(GAME_ROUNDS_FILE, {})

    if not wolves:
        return None

    # =====================================
    # RANDOM SPEAK ORDER (same for all rounds)
    # =====================================
    speak_order = wolves[:]
    random.shuffle(speak_order)

    current_round = game_round.get("current_round", 0)

    # =====================================
    # DISCUSSION SYSTEM PROMPT
    # =====================================
    SYSTEM_PROMPT_DISCUSSION = """
        You are simulating a character in a structured social deduction game.
        Your character's role is werewolf, you are discussing with other werewolves to decide on a target to kill tonight.
        Now it's your turn to speak, your speech will be presented to the other werewolves and potentially impact their decisions.
        You may share suspicions, support plans, disagree, persuade, propose, or mislead strategically.

        Rules:
        - You MUST only use the information provided in the input.
        - You MUST NOT assume, invent, or hallucinate any information not present.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to reason and speak.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 200 characters.
        - Then present your speech to other werewolves; the MAXIMUM length is 300 characters, any excess will be truncated.
        - Be PRECISE and CONCISE.

        Return STRICT JSON in this format:
        {
        "reasoning": "",
        "speech": ""
        }
    """

    # =====================================
    # 3 ROUNDS PRIVATE DISCUSSION
    # =====================================
    for discuss_round in range(1, 4):

        for speaker in speak_order:
            # skip dead during phase (future-proof)
            if chars["characters"][speaker]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(chars, speaker)
            valid_targets = get_valid_targets(exclude=[])
            valid_vote_options = valid_targets + ["no_kill"]

            prompt_payload = {
                "character_information": view,
                "introduction": "This is the night phase, werewolves have three rounds of private discussion to coordinate and decide on a target to kill. This is round " + str(discuss_round) + " of the discussion.",
                "reminder": "Your objective is to help Team Werewolf win the game. Consider carefully what you say, as it may determine the target tonight and ultimately which team wins the game.",
                "VALID_targets": valid_vote_options
            }

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_DISCUSSION},
                        {"role": "user", "content": json.dumps(prompt_payload)}
                    ]
                )

                content = response.choices[0].message["content"]
                content = content.replace("```json", "").replace("```", "").strip()
                data = json.loads(content)

                reasoning = data.get("reasoning", "")[:200]
                speech = data.get("speech", "")[:300]

            except:
                reasoning = ""
                speech = "..."

            # ---------------------------------
            # speaker remembers own action
            # ---------------------------------
            chars["characters"][speaker]["memory"]["recent"][
                f"round_{current_round}_night_wolfchat_{discuss_round}_spoke"
            ] = {
                "description": {
                    "actor": speaker,
                    "action": "spoke in werewolf private discussion",
                    "speech": speech,
                    "reasoning": reasoning
                },
                "impact": 100
            }

            # ---------------------------------
            # other wolves hear + remember
            # ---------------------------------
            for listener in wolves:
                if listener == speaker:
                    continue
                if chars["characters"][listener]["game_status"]["is_dead"]:
                    continue

                chars["characters"][listener]["memory"]["recent"][
                    f"round_{current_round}_night_wolfchat_{discuss_round}_heard"
                ] = {
                    "description": {
                        "actor": listener,
                        "action": f"heard {speaker} speak in werewolf private discussion. {speaker} said: '{speech}'",
                    },
                    "impact": 80
                }

            save_json(CHARACTERS_FILE, chars)

    # =====================================
    # VOTING PHASE
    # =====================================
    SYSTEM_PROMPT_VOTE = """
        You are simulating a character in a structured social deduction game.
        Your character's role is werewolf, you've discussed with other werewolves, now it's time to decide and vote on a target to kill tonight.

        Rules:
        - You MUST only use the information provided in the input.
        - You MUST NOT assume, invent, or hallucinate any information not present.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to decide and vote.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 200 characters, any excess will be truncated.
        - Then provide your final vote decision for the target to kill tonight. 
        - your vote decision MUST be within the given target range, otherwise it will be counted as "no_kill".

        Return STRICT JSON in this format:
        {
        "reasoning": "",
        "vote": ""
        }
    """

    votes = {}

    for wolf in wolves:

        if chars["characters"][wolf]["game_status"]["is_dead"]:
            continue

        view = build_llm_view(chars, wolf)

        valid_targets = get_valid_targets(exclude=[])
        valid_vote_options = valid_targets + ["no_kill"]

        prompt_payload = {
            "character_information": view,
            "introduction": "This is the night phase, werewolves' discussion is concluded, now it's time to vote on a target",
            "reminder": "Your objective is to help Team Werewolf win the game. Consider carefully who you vote on and if it will be effective, as it may determine the target tonight and ultimately which team wins the game.",
            "VALID_targets": valid_vote_options
        }

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_VOTE},
                    {"role": "user", "content": json.dumps(prompt_payload)}
                ]
            )

            content = response.choices[0].message["content"]
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

            reasoning = data.get("reasoning", "")[:200]
            answer = str(data.get("vote", "")).strip()

        except:
            reasoning = ""
            answer = "no_kill"

        if answer not in valid_vote_options:
            answer = "no_kill"

        votes[answer] = votes.get(answer, 0) + 1

        chars["characters"][wolf]["memory"]["recent"][
            f"round_{current_round}_night_wolfvote"
        ] = {
            "description": {
                "actor": wolf,
                "action": f"voted for {answer} as the target to kill this night",
                "vote": answer,
                "reasoning": reasoning
            },
            "impact": 100
        }

        # ---------------------------------
        # other wolves get the result of this vote too
        # ---------------------------------
        for observer in wolves:
            if observer == wolf:
                continue
            if chars["characters"][observer]["game_status"]["is_dead"]:
                continue

            chars["characters"][observer]["memory"]["recent"][
                f"round_{current_round}_night_wolfvote_observed"
            ] = {
                "description": {
                    "actor": observer,
                    "action": f"observed {wolf} vote {answer} as the target to kill this night",
                },
                "impact": 100
            }
        
        save_json(CHARACTERS_FILE, chars)

    # =====================================
    # RESOLVE VOTE
    # =====================================
    if not votes:
        save_json(CHARACTERS_FILE, chars)
        return None

    highest = max(votes.values())
    top = [name for name, count in votes.items() if count == highest]

    # tie = no kill
    if len(top) != 1:
        result = None
    else:
        result = top[0]

    if result == "no_kill":
        result = None
    
    # =====================================
    # SHARE VOTING RESULTS TO ALL WOLVES
    # =====================================
    for wolf in wolves:
        if chars["characters"][wolf]["game_status"]["is_dead"]:
            continue

        chars["characters"][wolf]["memory"]["recent"][
            f"round_{current_round}_night_wolfvote_result"
        ] = {
            "description": {
                "actor": wolf,
                "action": "observed werewolf voting results",
                "votes": votes,
                "final_target": result if result else "no_kill"
            },
            "impact": 100
        }

    save_json(CHARACTERS_FILE, chars)
    return result

# =========================
# GAME PHASES - NIGHT
# =========================
def night_phase():
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    game = load_json(GAME_ROUNDS_FILE, {})

    night_state = {
        "seer_target": None,
        "werewolf_target": None,
        "guardian_target": None,
        "witch_poison_target": None,
        "hunter_shot": None
    }

    # =========================
    # 1. SEER
    # =========================
    seer = get_alive_role(chars, "seer")
    if seer:
        target = ask_llm_for_target(seer, "seer", None)

        if is_valid_target(target, chars):
            night_state["seer_target"] = target

            # ---- reveal team ----
            team = chars["characters"][target]["game_status"]["team"]
            seer_char = chars["characters"][seer]
            seer_char["knowledge"]["characters"][target]["game_status"]["team"] = {
                "value": team,
                "confidence": 100
            }

    # =========================
    # 2. WEREWOLVES
    # =========================
    wolves = get_alive_roles(chars, "werewolf")
    if wolves:
        target = ask_llm_for_target_wolves(wolves, "werewolf", None)

        if is_valid_target(target, chars):
            night_state["werewolf_target"] = target

    # =========================
    # 3. GUARDIAN ANGEL
    # =========================
    guardian = get_alive_role(chars, "guardian_angel")
    if guardian:
        char = chars["characters"][guardian]
        last = char["game_status"]["ability"].get("last_protected")

        target = ask_llm_for_target(guardian, "guardian_angel", None)

        if target != last and is_valid_target(target, chars):
            night_state["guardian_target"] = target
            char["game_status"]["ability"]["last_protected"] = target
    
    # =========================
    # RESOLVE WEREWOLVES & GUARDIAN ANGEL BEFORE WITCH
    # =========================
    if night_state["werewolf_target"] and night_state["werewolf_target"] == night_state["guardian_target"]:
        night_state["werewolf_target"] = None
    night_state["guardian_target"] = None

    # =========================
    # 4. WITCH
    # =========================
    witch = get_alive_role(chars, "witch")
    if witch:
        char = chars["characters"][witch]
        ability = char["game_status"]["ability"]

        wolf_target = night_state["werewolf_target"]
        # ---- SAVE ----
        if wolf_target and ability.get("save_potion", 0) > 0:
            use_save = ask_llm_for_target(witch, "witch_save", wolf_target)
            if use_save:
                night_state["werewolf_target"] = None
                ability["save_potion"] -= 1

        # ---- POISON ----
        if ability.get("poison_potion", 0) > 0:
            poison_target = ask_llm_for_target(witch, "witch_poison", None)

            if is_valid_target(poison_target, chars):
                night_state["witch_poison_target"] = poison_target
                ability["poison_potion"] -= 1

    # =========================
    # 5. HUNTER
    # =========================
    wolf_target = night_state["werewolf_target"]
    if wolf_target and chars["characters"][wolf_target]["game_status"]["role"] == "hunter":
        shot = ask_llm_for_target(wolf_target, "hunter", None)

        if is_valid_target(shot, chars):
            night_state["hunter_shot"] = shot

    # =========================
    # 6. RESOLUTION
    # =========================
    deaths = set()

    wolf_target = night_state["werewolf_target"]
    # ---- apply werewolf kill ----
    if wolf_target:
        deaths.add(wolf_target)

    # ---- poison ----
    if night_state["witch_poison_target"]:
        deaths.add(night_state["witch_poison_target"])

    # ---- hunter ----
    if night_state["hunter_shot"]:
        deaths.add(night_state["hunter_shot"])

    # ---- apply deaths ----
    for name in deaths:
        char = chars["characters"][name]
        char["game_status"]["is_dead"] = True

    # =====================================
    # MORNING ANNOUNCEMENT
    # =====================================
    current_round = game.get("current_round", 0)

    # prepare announcement
    if deaths:
        announcement_text = f"Morning announcement: The following players died last night: {', '.join(deaths)}."
    else:
        announcement_text = "Morning announcement: No one died last night."

    for name, char in chars["characters"].items():
        # dead players don't receive updates
        if char["game_status"]["is_dead"]:
            continue
        # ---------------------------------
        # MEMORY LOG
        # ---------------------------------
        char["memory"]["recent"][f"round_{current_round}_morning_announcement"] = {
            "description": {
                "type": "game_announcement",
                "content": announcement_text,
                "deaths": list(deaths)
            },
            "impact": 100
        }
        # ---------------------------------
        # KNOWLEDGE UPDATE
        # ---------------------------------
        for dead_name in deaths:
            char["knowledge"]["characters"][dead_name]["game_status"]["is_dead"] = {
                "value": True,
                "confidence": 100
            }

    # =========================
    # SAVE
    # =========================
    save_json(CHARACTERS_FILE, chars)

def day_phase():
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    game = load_json(GAME_ROUNDS_FILE, {})

    current_round = game.get("current_round", 0)

    # =====================================
    # GET ALIVE PLAYERS
    # =====================================
    alive_players = [
        name for name, c in chars["characters"].items()
        if not c["game_status"]["is_dead"]
    ]

    if len(alive_players) <= 1:
        return

    # =====================================
    # RANDOM SPEAK ORDER (fixed for day)
    # =====================================
    speak_order = alive_players[:]
    random.shuffle(speak_order)

    interrupt_triggered = False

    # =====================================
    # SYSTEM PROMPT
    # =====================================
    SYSTEM_PROMPT_SPEECH = """
        You are simulating a character in a structured social deduction game.

        You are in a public discussion where players try to decide who to eliminate.
        Other players may lie. You must reason carefully.

        Rules:
        - Use ONLY the provided information.
        - Do NOT invent facts.
        - Stay consistent with your personality, goals, and knowledge.

        Output:
        {
        "reasoning": "",
        "speech": "",
        }
    """

    SYSTEM_PROMPT_CHALLENGE = """
        You are simulating a character in a social deduction game.

        You are the Knight. You may challenge ONE player in the entire game.

        Rules:
        - Only challenge if you believe it significantly improves your team's chance of winning.
        - If you challenge:
        - If target is a werewolf → they die
        - Otherwise → BOTH you and target die
        - This action immediately ends the day (no vote)

        Constraints:
        - Use ONLY provided information
        - Do NOT invent facts

        Output STRICT JSON:
        {
        "reasoning": "max 200 chars",
        "answer": "target_name OR no"
        }
    """

    SYSTEM_PROMPT_REVEAL = """
        You are simulating a character in a social deduction game.

        You are a Werewolf. You may reveal yourself publicly.

        Rules:
        - If you reveal:
        - You die immediately
        - The day ends (no vote)
        - Only reveal if it benefits the werewolf team strategically

        Constraints:
        - Use ONLY provided information
        - Do NOT invent facts

        Output STRICT JSON:
        {
        "reasoning": "max 200 chars",
        "answer": "yes OR no"
        }
    """

    # =====================================
    # DISCUSSION ROUNDS
    # =====================================
    for discuss_round in [1, 2]:

        for speaker in speak_order:
            # skip dead mid-phase
            if chars["characters"][speaker]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(chars, speaker)
            role = chars["characters"][speaker]["game_status"]["role"]
            valid_targets = get_valid_targets(exclude=speaker)

            # =====================================
            # KNIGHT INTERRUPT
            # =====================================
            if role == "knight":
                ability = chars["characters"][speaker]["game_status"]["ability"]

                if ability.get("challenge_chance", 0) > 0:
                    challenge_prompt = {
                        "character_information": view,
                        "question": "Do you want to challenge a player? If yes, choose a target. If no, answer 'no'.",
                        "valid_options": valid_targets + ["no"]
                    }

                    try:
                        response = client.chat.completions.create(
                            model=MODEL,
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT_CHALLENGE},
                                {"role": "user", "content": json.dumps(challenge_prompt)}
                            ]
                        )
                        data = json.loads(response.choices[0].message["content"])
                        answer = data.get("answer", "no")

                    except:
                        answer = "no"

                    if answer != "no" and answer in valid_targets:
                        ability["challenge_chance"] = 0

                        target_role = chars["characters"][answer]["game_status"]["role"]

                        if target_role == "werewolf":
                            chars["characters"][answer]["game_status"]["is_dead"] = True
                        else:
                            chars["characters"][answer]["game_status"]["is_dead"] = True
                            chars["characters"][speaker]["game_status"]["is_dead"] = True

                        interrupt_triggered = True

                        # memory log (all alive)
                        for name, c in chars["characters"].items():
                            if c["game_status"]["is_dead"]:
                                continue

                            c["memory"]["recent"][f"round_{current_round}_knight_challenge"] = {
                                "description": {
                                    "actor": speaker,
                                    "target": answer,
                                    "result": "success" if target_role == "werewolf" else "both_dead"
                                },
                                "impact": 100
                            }

                        break

                    if answer == "no":
                        chars["characters"][speaker]["memory"]["recent"][
                            f"round_{current_round}_knight_no_challenge"
                        ] = {
                            "description": {
                                "actor": speaker,
                                "action": "chose not to use knight challenge",
                                "reasoning": reasoning
                            },
                            "impact": 60
                        }
                    
                    save_json(CHARACTERS_FILE, chars)

            # =====================================
            # WEREWOLF REVEAL
            # =====================================
            if role == "werewolf":
                reveal_prompt = {
                    "character_information": view,
                    "question": "Do you want to reveal yourself as a werewolf? Answer yes or no.",
                    "valid_options": ["yes", "no"]
                }

                try:
                    response = client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT_REVEAL},
                            {"role": "user", "content": json.dumps(reveal_prompt)}
                        ]
                    )
                    data = json.loads(response.choices[0].message["content"])
                    answer = data.get("answer", "no")

                except:
                    answer = "no"

                if answer == "yes":
                    chars["characters"][speaker]["game_status"]["is_dead"] = True
                    interrupt_triggered = True

                    for name, c in chars["characters"].items():
                        if c["game_status"]["is_dead"]:
                            continue

                        c["memory"]["recent"][f"round_{current_round}_werewolf_reveal"] = {
                            "description": {
                                "actor": speaker,
                                "action": "revealed as werewolf and died"
                            },
                            "impact": 100
                        }

                    break

                if answer == "no":
                    chars["characters"][speaker]["memory"]["recent"][
                        f"round_{current_round}_werewolf_no_reveal"
                    ] = {
                        "description": {
                            "actor": speaker,
                            "action": "chose not to reveal as werewolf",
                        },
                        "impact": 60
                    }
                
                save_json(CHARACTERS_FILE, chars)

            view = build_llm_view(chars, speaker)

            payload = {
                "character_information": view,
                "phase": "day_discussion",
                "discuss_round": discuss_round,
                "audiences": valid_targets
            }

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_SPEECH},
                        {"role": "user", "content": json.dumps(payload)}
                    ]
                )

                content = response.choices[0].message["content"]
                content = content.replace("```json", "").replace("```", "").strip()
                data = json.loads(content)

                reasoning = data.get("reasoning", "")[:200]
                speech = data.get("speech", "")[:300]

            except:
                reasoning, speech = "", "..."

            # =====================================
            # MEMORY LOG (SELF)
            # =====================================
            chars["characters"][speaker]["memory"]["recent"][
                f"round_{current_round}_day_discuss_{discuss_round}_spoke"
            ] = {
                "description": {
                    "type": "day_discussion",
                    "actor": speaker,
                    "action": f"spoke in day discussion round {discuss_round}",
                    "speech": speech,
                    "reasoning": reasoning
                },
                "impact": 100
            }

            # =====================================
            # MEMORY LOG (OTHERS HEAR)
            # =====================================
            for listener in speak_order:
                if listener == speaker:
                    continue
                if chars["characters"][listener]["game_status"]["is_dead"]:
                    continue

                chars["characters"][listener]["memory"]["recent"][
                    f"round_{current_round}_day_discuss_{discuss_round}_heard"
                ] = {
                    "description": {
                        "type": "day_discussion",
                        "actor": listener,
                        "action": f"heard {speaker} speak in day discussion. {speaker} said: '{speech}'",
                    },
                    "impact": 80
                }

            save_json(CHARACTERS_FILE, chars)

        if interrupt_triggered:
            break

    # =====================================
    # VOTING PHASE
    # =====================================
    if not interrupt_triggered:

        SYSTEM_PROMPT_VOTE = """
        You are simulating a character deciding who to eliminate.

        Rules:
        - Use ONLY given information.
        - Do NOT invent facts.

        Output:
        {
          "reasoning": "",
          "vote": ""
        }
        """

        votes = {}

        for voter in speak_order:

            if chars["characters"][voter]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(voter)

            valid_targets = get_valid_targets()
            valid_options = valid_targets + ["abstain"]

            payload = {
                "character_information": view,
                "valid_options": valid_options
            }

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_VOTE},
                        {"role": "user", "content": json.dumps(payload)}
                    ]
                )

                content = response.choices[0].message["content"]
                content = content.replace("```json", "").replace("```", "").strip()
                data = json.loads(content)

                reasoning = data.get("reasoning", "")[:200]
                vote = str(data.get("vote", "")).strip()

            except:
                reasoning = ""
                vote = "abstain"

            if vote not in valid_options:
                vote = "abstain"

            votes[vote] = votes.get(vote, 0) + 1

            # memory self
            chars["characters"][voter]["memory"]["recent"][
                f"round_{current_round}_day_vote"
            ] = {
                "description": {
                    "actor": voter,
                    "vote": vote,
                    "reasoning": reasoning
                },
                "impact": 100
            }

            for listener in speak_order:
                if listener == voter:
                    continue
                if chars["characters"][listener]["game_status"]["is_dead"]:
                    continue

                chars["characters"][listener]["memory"]["recent"][
                    f"round_{current_round}_day_vote_observe"
                ] = {
                    "description": {
                        "actor": listener,
                        "action": f"saw {voter} vote for {vote}"
                    },
                    "impact": 80
                }

            save_json(CHARACTERS_FILE, chars)

        # =====================================
        # RESOLVE VOTE
        # =====================================
        if votes:
            highest = max(votes.values())
            top = [k for k, v in votes.items() if v == highest]

            if len(top) == 1 and top[0] != "abstain":
                eliminated = top[0]
                chars["characters"][eliminated]["game_status"]["is_dead"] = True
            else:
                eliminated = None
        else:
            eliminated = None

        # =====================================
        # SHARE RESULT MEMORY
        # =====================================
        for name, char in chars["characters"].items():
            if char["game_status"]["is_dead"]:
                continue

            char["memory"]["recent"][f"round_{current_round}_day_vote_result"] = {
                "description": {
                    "votes": votes,
                    "result": eliminated if eliminated else "no_elimination"
                },
                "impact": 100
            }

    save_json(CHARACTERS_FILE, chars)

def check_win_conditions(chars):
    alive = [
        c for c in chars["characters"].values()
        if not c["game_status"]["is_dead"]
    ]

    werewolves_alive = [
        c for c in alive
        if c["game_status"]["team"] == "werewolf"
    ]

    villagers_alive = [
        c for c in alive
        if c["game_status"]["team"] == "village"
    ]

    if len(werewolves_alive) == 0 and len(villagers_alive) == 0:
        return "tie"

    if len(werewolves_alive) == 0:
        return "village_win"

    if len(villagers_alive) == 0:
        return "werewolf_win"

    return None

# =========================
# MAIN LOOP
# =========================
def main():
    init_files()

    # ---- game setup ----
    initialize_game_state()
    CHARACTER_NAMES = ["AA", "CO", "DO", "FO", "GA", "LO", "MA", "NO", "PA", "SA", "TO", "VA", "WA", "YA"]
    initialize_characters(CHARACTER_NAMES)
    initialize_characters_scene_world()

    game = load_json(GAME_ROUNDS_FILE, {})
    game["current_round"] = 1
    save_json(GAME_ROUNDS_FILE, game)

    while True:
        night_phase()
        if check_win_conditions():
            break
        day_phase()
        if check_win_conditions():
            break
        
        game = load_json(GAME_ROUNDS_FILE, {})
        game["current_round"] += 1
        save_json(GAME_ROUNDS_FILE, game)
    

    # memory_manager = MemoryManager()

    # TIME/TIMESTAMP - IN-WORLD TIME - BIG ISSUE UNRESOLVED YET

    # LAST ROUND's events
    events = []
    while True:
        # player_action usage??? what input do you want/to use here???
        player_action = input("actions or words: ").strip()
        if player_action.lower() == "exit":
            break

        # Detect if the player is describing a new character
        detect_and_create_character_from_input(player_action)

        # Load characters, scene
        chars = load_json(CHARACTERS_FILE, {"characters": {}}).get("characters", {})
        scene = load_json(SCENE_STATE_FILE, scene_template())

        # Merge into previous events for perception
        perception_input_events = events

        # ------------------------
        # 1. BUILD PERCEPTION (from PREVIOUS round)
        # ------------------------
        perception = build_perception(perception_input_events, scene)

        # ------------------------
        # 2. EACH CHARACTER DECIDES & ACTS
        # ------------------------
        all_character_outputs = {}
        for char_name, perceived in perception.items():
            if char_name not in chars:
                continue
            # ??? Not known characters...? but...? how about new characters...? potentially problematic here
            result = character_decision_and_action(char_name, perceived)
            if result:
                all_character_outputs[char_name] = result
        
        # ------------------------
        # 3. CONVERT OUTPUTS → EVENTS (NEW ROUND EVENTS)
        # ------------------------
        new_events = []
        for char_name, output in all_character_outputs.items():
            evs = convert_output_to_events(char_name, output)
            for e in evs:
                e = normalize_and_validate_event(e)
                if e:
                    new_events.append(e)
        
        # ------------------------
        # 4. PROCESS EVENTS -> UPDATE SCENE
        # ------------------------
        current_time = scene["time"]["elapsed_hours"]
        scene = process_events_into_scene(new_events, scene, current_time)
        # TIME?!! TIMESTAMP?!! DID I HANDLE?!! HOW?!!

        # ------------------------
        # 5. ESTIMATE TIME FROM EVENTS
        # ------------------------
        hours = estimate_time_from_events(new_events)
        scene["time"]["elapsed_hours"] += hours
        # update time_of_day
        scene["time"]["time_of_day"] = update_time_of_day(scene["time"]["time_of_day"], hours)
        save_json(SCENE_STATE_FILE, scene)

        # # ------------------------
        # # 6. BUILD PERCEPTION (from NEW EVENTS)
        # # ------------------------
        # update_events = perception_input_events
        # new_perception = build_perception(update_events, scene)
        
        # ------------------------
        # 6. UPDATE CHARACTERS FROM PERCEPTION
        # A LAG/DELAY OF PERCEPTION->ACTION->UPDATING PERCEPTION BEFORE ACTION
        # CHECK: IS EACH EVENT USED EXACTLY ONCE FOR EACH PROCESS?
        # ------------------------
        for char_name, perceived in perception.items():
            update_character_from_perception(char_name, perceived)
        
        # ------------------------
        # 7. SAVE EVENTS FOR NEXT ROUND
        # ------------------------
        events = new_events

        # ------------------------
        # 8. DECAY MEMORY & KNOWLEDGE
        # ------------------------
        hours = estimate_time_from_events(new_events)
        for char in chars.values():
            decay_memory(char, hours)
            decay_knowledge(char, hours)

        # # ------------------------
        # # THEN generate story
        # # BUT- BUT- THE NARRATOR SHOULDN'T BE GIVEN ALL INFORMATION (AT ONCE) EITHER?!! ONE BY ONE TOO...?
        # # ------------------------
        # story_output = generate_story("??? FOR NOW")
        # print("\n--- Story Output ---\n")
        # print(story_output)
        # print("\n--------------------\n")

        # # Log story output
        # timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # append_text(CHAPTER_LOG_FILE, f"[{timestamp}] CHAPTER:\n{story_output}\n")

        # # Auto-update world, scene from explicit text
        # # !!! Problematic old ver. needs to be modified here
        # update_world_from_output(story_output)

        # # Summarize and update memory
        # summary = summarize_output_for_memory(story_output)
        # memory_manager.add_event_summary(summary)

if __name__ == "__main__":
    main()
