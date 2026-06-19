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
    visual_events = generate_visual_events(scene, chars_all)

    # merge them into events
    events = visual_events + events

    scene_chars = set(scene.get("characters_present", {}).keys())

    # initialize ONLY scene characters first
    for c in scene_chars:
        perception[c] = {}
    
    public_info = extract_public_scene_info(scene)
    for c in scene_chars:
        perception[c] = {
            "__scene__": public_info
        }

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

        "knowledge_bits": {}
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
        "activity": ""
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
    result = {
        "scene": perceived_events.get("__scene__", {}),
        "events": []
    }
    for eid, pdata in perceived_events.items():
        if eid == "__scene__":
            continue
        e = pdata.get("event", {})
        result["events"].append({
            "id": eid,
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
# MAIN LOOP
# =========================
def main():
    init_files()

    initialize_characters_with_world_knowledge()

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
