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
STYLE_GUIDE_FILE = os.path.join(DATA_DIR, "style_guide.txt")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.json")
SCENE_STATE_FILE = os.path.join(DATA_DIR, "scene_state.json")
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
        
#=======HELPERS=======
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
        save_json(WORLD_BIBLE_FILE, {
            "setting": {},
            "rules": {},
            "tone": "",
            "themes": {},
            "factions": {},
            "cultures": {},
            "important_places": {},
            "important_events": [],   
        })

    if not os.path.exists(STYLE_GUIDE_FILE):
        save_text(STYLE_GUIDE_FILE, "")

    if not os.path.exists(CHARACTERS_FILE):
        save_json(CHARACTERS_FILE, {"characters": {}})

    if not os.path.exists(SCENE_STATE_FILE):
        save_json(SCENE_STATE_FILE, {
            "location": {
                "key": "",
                "name": "",
                "description": ""
            },
            "time": {
                "time_of_day": "",
                "elapsed_hours": 0.0
            },
            "environment": {
                "weather": {"description": "", "severity": 0},
                "atmosphere": {
                    "sensory": {"description": "", "value": 0},
                    "emotional": {"description": "", "value": 0},
                    "social": {"description": "", "value": 0}
                }
            },
            "narrative": {
                "objective": {"description": "", "priority": 0},
                "stakes": {"description": "", "severity": 0},
                "constraints": {}
            },
            "dynamics": {
                "danger_level": 0,
                "tension": 0
            },
            "characters_present": {},   # name -> {"focus": 0-100}
            "focus": {},                # name -> weight
            "objects": {},              # already good
            "conflicts": {},            # conflict_key -> {...}
            "events": {}                # event_key -> {...}
        })

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
# MEMORY MANAGER
# =========================
class MemoryManager:
    def __init__(self):
        self.short = load_json(SHORT_MEMORY_FILE, {"summaries": []})
        self.medium = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
        self.long = load_json(LONG_ARCHIVE_FILE, {"summaries": []})
        self.long_summary = load_text(LONG_SUMMARY_FILE, "")

    def add_event_summary(self, summary_text):
        self.short["summaries"].append(summary_text)
        if len(self.short["summaries"]) > 6:
            rolled = self.short["summaries"].pop(0)
            self.medium["summaries"].append(rolled)

        self.long["summaries"].append(summary_text)

        save_json(SHORT_MEMORY_FILE, self.short)
        save_json(MEDIUM_MEMORY_FILE, self.medium)
        save_json(LONG_ARCHIVE_FILE, self.long)

        self.update_long_summary()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_text(EVENT_LOG_FILE, f"[{timestamp}] EVENT SUMMARY: {summary_text}")

    def update_long_summary(self):
        recent = self.long["summaries"][-20:]
        if not recent:
            text = "So far, nothing significant has happened yet."
        else:
            text = "So far in the story: " + " ".join(recent)
        self.long_summary = text
        save_text(LONG_SUMMARY_FILE, text)

# =========================
# PROMPT BUILDER
# =========================
def build_prompt(player_action):
    world = load_json(WORLD_BIBLE_FILE, {})
    style = load_text(STYLE_GUIDE_FILE, "")
    chars = load_json(CHARACTERS_FILE, {})
    scene = load_json(SCENE_STATE_FILE, {})
    short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
    medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
    long_summary = load_text(LONG_SUMMARY_FILE, "")
    player = load_json(PLAYER_FILE, {"player_character": ""})
    player_name = player.get("player_character", "").strip()

    short_block = "\n".join(f"- {s}" for s in short_mem["summaries"])
    medium_block = "\n".join(f"- {s}" for s in medium_mem["summaries"][-15:])

    system_instructions = (
        "You are a long-form roleplay storyteller.\n"
        "The user controls the player character.\n"
        "Write the story in third-person limited perspective, referring to the player-character by name.\n"
        "Interpret the user's input as the player character's direct actions, thoughts, or dialogue.\n"
        "Do not contradict or override the player's stated actions.\n"
        "Maintain strict continuity with the world, characters, and events.\n"
        "When describing character actions and reactions, use their weighted traits, goals, roles, "
        "physical and mental states, and relationships from the character sheets to keep behavior consistent.\n"
        "Do not recap the entire story every time; continue naturally from context.\n"
    )

    world_block = json.dumps(world, ensure_ascii=False, indent=2)
    chars_block = json.dumps(chars, ensure_ascii=False, indent=2)
    scene_block = json.dumps(scene, ensure_ascii=False, indent=2)

    full_prompt = (
        f"# Style Guide\n{style}\n\n"
        f"# World Bible\n{world_block}\n\n"
        f"# Character Sheets\n{chars_block}\n\n"
        f"# Scene State\n{scene_block}\n\n"
        f"# Long-Term Story Summary\n{long_summary}\n\n"
        f"# Short-Term Memory (Recent Events)\n{short_block}\n\n"
        f"# Medium-Term Memory (Older Events)\n{medium_block}\n\n"
        f"# Player Character\n{player_name if player_name else 'Unknown'}\n\n"
        f"# Player Action (what the user just did or said)\n{player_action}\n\n"
        "Continue the story in third-person limited POV, describing the consequences of this action, "
        "the reactions of the world and other characters, and the unfolding scene.\n"
    )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": full_prompt}
    ]
    return messages

def decide_character_action(character_name, situation_text):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})
    scene = load_json(SCENE_STATE_FILE, {})
    world = load_json(WORLD_BIBLE_FILE, {})
    short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
    medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
    long_summary = load_text(LONG_SUMMARY_FILE, "")

    if character_name not in chars_all.get("characters", {}):
        return ""

    char_sheet = chars_all["characters"][character_name]

    prompt = (
        "You are a decision-making assistant for a narrative simulation.\n\n"
        "Given:\n"
        "- the character sheet,\n"
        "- the current scene,\n"
        "- the world state,\n"
        "- ongoing projects,\n"
        "- short/medium memory,\n"
        "- the long-term summary,\n"
        "- and the situation text,\n\n"
        "determine what this character is most likely to do next.\n\n"
        "Use:\n"
        "- weighted properties (0-100)\n"
        "- weighted personality traits (0–100)\n"
        "- weighted goals (0–100)\n"
        "- weighted roles (0–100)\n"
        "- weighted abilities (0–100)\n"
        "- weighted interests and dislikes (0–100)\n"
        "- physical and mental state values (0–100)\n"
        "- relationships and their strength (0–100)\n"
        "- faction affiliations AND world faction relationships\n"
        "- place danger, tension, atmosphere, and conflicts\n"
        "- time passed (scene.last_segment_hours and scene.time_elapsed_total_hours)\n"
        "- ongoing projects (training, healing, construction, travel, etc.)\n"
        "- recent events (short/medium memory) and long-term summary\n\n"
        "NPCs have species, aging_rate, and may be immortal. These influence their physical_state, mental_state, "
        "abilities, roles, and long-term drift.\n"
        "NPCs must obey world rules from the world_bible (for example, if a rule disables an ability after killing, "
        "they should treat that ability as unusable).\n"
        "NPCs may wield or use their possessions according to the descriptions and values of the possessions reasonably.\n"
        "NPCs may introduce or interact with new characters, places, factions, and events when it makes narrative sense.\n\n"
        "NPCs may:\n"
        "- travel between important_places when it fits their goals or relationships.\n"
        "- act according to faction politics (help allies, sabotage enemies, avoid or manipulate neutrals).\n"
        "- evolve relationships (trust, resentment, affection) based on events and memory.\n"
        "- update or abandon goals when old goals are achieved, blocked, or made irrelevant.\n"
        "- escalate or resolve conflicts in scene_state.ongoing_conflicts.\n"
        "- continue, pause, or abandon ongoing projects depending on time, personality, state, and world events.\n"
        "- react to world instability, danger, or opportunity.\n"
        "- be interrupted by major events (rebellion, attack, disaster) and change plans accordingly.\n\n"
        "NPCs do NOT see numeric world values. They infer danger, instability, or opportunity based on descriptions "
        "and their own personal biases:\n"
        "- optimists underestimate risk,\n"
        "- pessimists overestimate it,\n"
        "- scholars estimate accurately,\n"
        "- impulsive characters ignore risk,\n"
        "- cautious characters avoid it.\n\n"
        "Respect continuity:\n"
        "- If the character is angry, depressed, injured, or afraid, they should not suddenly act fine without reason.\n"
        "- If they started a long-term project, they should continue unless something interrupts them.\n"
        "- If they have a grudge, it persists.\n"
        "- If they have a bond, it influences choices.\n\n"
        "First, briefly explain the reasoning in 2–3 sentences.\n"
        "Then, on a new line starting with 'ACTION:', describe the concrete action they take.\n"
    )

    payload = {
        "character_name": character_name,
        "character_sheet": char_sheet,
        "scene_state": scene,
        "world_bible": world,
        "short_memory": short_mem,
        "medium_memory": medium_mem,
        "long_summary": long_summary,
        "situation": situation_text
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
        ]
    )

    return response.choices[0].message["content"]

# =========================
# GROQ CALL: STORY GENERATION
# =========================
def generate_story(player_action):
    messages = build_prompt(player_action)
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )
    return response.choices[0].message["content"]

# =========================
# GROQ CALL: SUMMARIZE OUTPUT
# =========================
def summarize_output_for_memory(output_text):
    summary_prompt = (
        "Summarize the following story segment into 1-2 concise sentences, "
        "focusing only on key events and changes in character or world state:\n\n"
        f"{output_text}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": summary_prompt}
        ]
    )
    return response.choices[0].message["content"].strip()

def estimate_time_passage(story_output):
    """
    Ask the model to estimate how many HOURS of in-world time passed in this story segment.
    """
    prompt = (
        "You are an assistant that estimates in-world time passage.\n"
        "Given a story segment, estimate approximately how many HOURS of in-world time passed.\n"
        "Consider pacing, described time skips, travel, and activities.\n"
        "Return STRICT JSON: {\"hours\": number}.\n"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": story_output}
        ]
    )

    content = response.choices[0].message["content"]
    try:
        data = json.loads(content)
        hours = data.get("hours", 0)
        if isinstance(hours, (int, float)):
            return float(hours)
    except:
        pass

    return 0.0

# =========================
# GROQ CALL: CHARACTER DECISION-MAKING
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

    if e.get("type") not in ["thought", "speech", "action"]:
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

    e["metadata"]["intensity"] = clamp_int(
        e["metadata"].get("intensity", 0), 0, 100, 0
    )

    return attach_event_id(e)

def build_perception(events, scene):
    # NOW IS USING OBJECTIVE EVENTS, NOT CHARACTER-INTERPRETED PERCEPTIONS
    perception = {}

    scene_chars = set(scene.get("characters_present", {}).keys())

    # initialize ONLY scene characters first
    for c in scene_chars:
        perception[c] = {}

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

def update_character_from_perception(char_name, perceived_events):
    chars_all = load_json(CHARACTERS_FILE, {"characters": {}})

    if char_name not in chars_all.get("characters", {}):
        return

    char_sheet = chars_all["characters"][char_name]

    # -------------------------
    # Build compact perception input
    # -------------------------
    # We only send minimal event info (not full raw structure)
    simplified_events = []

    for eid, pdata in perceived_events.items():
        event = pdata.get("event", {})
        simplified_events.append({
            "id": eid,
            "type": event.get("type", ""),
            "actor": event.get("actor", ""),
            "target": event.get("target", []),
            "content": event.get("content", ""),
            "confidence": pdata.get("confidence", 0)
        })

    # -------------------------
    # Prompt (STRICT)
    # -------------------------
    prompt = (
        "You are updating a character's state based ONLY on what they perceived.\n\n"

        "STRICT RULES:\n"
        "1. ONLY use the provided perception events.\n"
        "2. DO NOT infer hidden traits, personality, or long-term conditions from a single event.\n"
        "3. DO NOT generalize (e.g., coughing does NOT mean weak or sickly personality).\n"
        "4. Prefer updating:\n"
        "   - memory (what happened)\n"
        "   - knowledge (what they believe happened, with confidence)\n"
        "   - immediate physical_state or mental_state IF directly observable\n"
        "5. DO NOT update:\n"
        "   - personality\n"
        "   - core properties\n"
        "   - long-term traits\n"
        "6. If uncertain, use LOW confidence or skip.\n"
        "7. DO NOT invent details not present in perception.\n\n"

        "Return STRICT JSON with this schema:\n"
        +character_information_extract_prompt()+
        "\n\nOnly include fields that actually changed.\n"
        "If nothing changed, return {\"characters\": {}}.\n"
    )

    payload = {
        "character_name": char_name,
        "character_sheet": char_sheet,
        "perceived_events": simplified_events
    }

    # -------------------------
    # Call LLM
    # -------------------------
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
        ]
    )

    content = response.choices[0].message["content"]

    try:
        updates = json.loads(content)
    except json.JSONDecodeError:
        return

    if "characters" not in updates:
        return

    # -------------------------
    # SAFETY FILTER
    # -------------------------
    ALLOWED_FIELDS = {
        "memory",
        "knowledge",
        "mental_state",
        "physical_state"
    }

    def filter_changes(changes):
        return {
            k: v for k, v in changes.items()
            if k in ALLOWED_FIELDS
        }

    # -------------------------
    # Apply updates
    # -------------------------
    for name, changes in updates["characters"].items():
        if name != char_name:
            continue

        safe_changes = filter_changes(changes)

        merge_character_changes(chars_all, name, safe_changes)

    save_json(CHARACTERS_FILE, chars_all)

# =========================
# GROQ CALL: CHARACTER UPDATES
# =========================
def knowledge_template():
    return {
        "characters": {},

        "world": {
            "places": {},
            "factions": {},
            "rules": {},
            "events": {}
        },

        "scene": {
            "location": {},
            "atmosphere": {},
            "events": {},
            "objects": {}
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
        "traits": {},
        "background": {},
        "interests": {},
        "dislikes": {},
        "goals": {},

        "relationships": {},

        "possessions": {},

        "state": {
            "location": {"value": None, "confidence": 0},
            "activity": {"description": "", "confidence": 0},
            "physical": {
                "aspect_key": {
                    "description": "",
                    "confidence": 0
                }
            },
            "mental": {
                "aspect_key": {
                    "description": "",
                    "confidence": 0
                }
            }
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
        "personal_projects": {},
        "abilities": {},
        "interests": {},
        "dislikes": {},
        "habits": {},

        "appearance": {},

        "physical_state": {},
        "mental_state": {},

        "faction_affiliations": {},

        "possessions": {},

        "relationships": {},

        "clothing": "",
        "location": "",
        "activity": ""
    }

# Example knowledge block
# (This is a reference/template, not used directly in the code)
#
# {
#     "B": {
#         "basics": {
#             "gender": {"value": "male", "confidence": 90},
#             "age_apparent": {"value": 25, "confidence": 60},
#             "age_actual": {"value": 25, "confidence": 40},
#             "species": {"value": "human", "confidence": 80},
#             "aging_rate": {"value": 1.0, "confidence": 50},
#             "is_immortal": {"value": false, "confidence": 50},
#             "appearance": {
#                 "description": "tall, dark hair",
#                 "confidence": 70
#             }
#         },
#         "role": {
#             "journalist": {"confidence": 75}
#         },
#         "traits": {
#             "writes_convincingly": {
#                 "description": "good at persuasive writing",
#                 "confidence": 80
#             }
#         },
#         "background": {
#             "origin": {
#                 "description": "from the North",
#                 "confidence": 50
#             }
#         },
#         "interests": {
#             "writing": {"confidence": 80}
#         },
#         "dislikes": {
#             "crowds": {"confidence": 60}
#         },
#         "goals": {
#             "publish_story": {"confidence": 40}
#         },
#         "relationships": {
#             "C": {
#                 "description": "childhood friend, distant now",
#                 "sentiment": -20,
#                 "confidence": 80
#             }
#         },
#         "possessions": {
#             "notebook": {"confidence": 80}
#         },
#         "state": {
#             "location": {"value": "city_square", "confidence": 90},
#             "activity": {
#                 "description": "writing notes",
#                 "confidence": 60
#             },
#             "physical": {},
#             "mental": {}
#         },
#         "knowledge_bits": {
#             "knows_poem_X": {
#                 "description": "knows a northern classical poem",
#                 "confidence": 60,
#                 "decay": "fast"
#             }
#         }
#     }
# }

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
        ### there's supposed to be knowledge here
        "      \"properties\": {\n"
        "        \"trait_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"personality\": {\n"
        "        \"trait_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"goals\": {\n"
        "        \"goal_key\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "      },\n"
        "      \"personal_projects\": {\n"
        "        \"project_key\": {\n"
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
        "        \"other_character\": {\"description\": \"string\", \"strength\": \"0-100\"}\n"
        "      },\n"
        "      \"clothing\": \"string (optional)\",\n"
        "      \"location\": \"string (optional)\",\n"
        "      \"activity\": \"string (optional)\"\n"

        "    }\n"
        "  }\n"
        "}"
    )

# knowledge extraction...that has nowhere to go yet...
# You MUST strictly follow this structure.
# Do NOT invent new categories or fields.
# Do NOT rename keys.
# If information does not fit, omit it.
# "      \"knowledge\": {\n"
# "        \"characters\": {\n"
# "          \"OtherCharacter\": {\n"
# "            \"basics\": {\n"
# "              \"gender\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
# "              \"age_apparent\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
# "              \"age_actual\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
# "              \"species\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
# "              \"aging_rate\": {\"value\": \"number\", \"confidence\": \"0-100\"},\n"
# "              \"is_immortal\": {\"value\": \"boolean\", \"confidence\": \"0-100\"},\n"
# "              \"appearance\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"role\": {\n"
# "              \"role_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"traits\": {\n"
# "              \"trait_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"background\": {\n"
# "              \"event_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"interests\": {\n"
# "              \"interest_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"dislikes\": {\n"
# "              \"dislike_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"goals\": {\n"
# "              \"goal_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"relationships\": {\n"
# "              \"OtherCharacter\": {\n"
# "                \"description\": \"string\",\n"
# "                \"sentiment\": \"-100 to 100\",\n"
# "                \"confidence\": \"0-100\"\n"
# "              }\n"
# "            },\n"
# "            \"possessions\": {\n"
# "              \"item_key\": {\"description\": \"string\", \"confidence\": \"0-100\"}\n"
# "            },\n"
# "            \"state\": {\n"
# "              \"location\": {\"value\": \"string\", \"confidence\": \"0-100\"},\n"
# "              \"activity\": {\"description\": \"string\", \"confidence\": \"0-100\"},\n"
# "              \"physical\": {\n"
# "                \"aspect_key\": {\n"
# "                  \"description\": \"string\",\n"
# "                  \"confidence\": \"0-100\"\n"
# "                }\n"
# "              },\n"
# "              \"mental\": {\n"
# "                \"aspect_key\": {\n"
# "                  \"description\": \"string\",\n"
# "                  \"confidence\": \"0-100\"\n"
# "                }\n"
# "              }\n"
# "            },\n"
# "            \"knowledge_bits\": {\n"
# "              \"key\": {\n"
# "                \"description\": \"string\",\n"
# "                \"confidence\": \"0-100\",\n"
# "                \"decay\": \"slow|medium|fast\"\n"
# "              }\n"
# "            }\n"
# "          }\n"
# "        },\n"
# "        \"world\": {},\n"
# "        \"scene\": {},\n"
# "        \"hard_knowledge\": {}\n"
# "      },\n"
#----------------------------------------

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
                    char["relationships"][other] = {"description": "", "strength": 0}
                if "description" in rdata:
                    char["relationships"][other]["description"] = rdata["description"]
                if "strength" in rdata:
                    char["relationships"][other]["strength"] = clamp_int(rdata["strength"], 0, 100, 0)
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

        if field == "personal_projects":
            if "personal_projects" not in char or not isinstance(char["personal_projects"], dict):
                char["personal_projects"] = {}
            for p_key, pdata in value.items():
                if p_key not in char["personal_projects"]:
                    char["personal_projects"][p_key] = {
                        "description": "",
                        "progress": 0,
                        "priority": 0
                    }
                if "description" in pdata:
                    char["personal_projects"][p_key]["description"] = pdata["description"]
                if "progress" in pdata:
                    char["personal_projects"][p_key]["progress"] = clamp_int(pdata["progress"], 0, 100, 0)
                if "priority" in pdata:
                    char["personal_projects"][p_key]["priority"] = clamp_int(pdata["priority"], 0, 100, 0)
            continue

    # fallback: ignore unknown fields safely (log them for debugging)
    # grouping & generic information kind may need to be modified to be more specific/complex later
    # this way the format/content for input information is very high-quality demanded and highly specific, be careful
    # add removal mechanism
    # the adding and labeling of the key...repetitive?
    # the replacing/covering problem of each update...old information...?
    # the structure overall is not so clean

def extract_events_from_decisions(npc_actions_text):
    prompt = (
        "You are an event extraction system.\n"
        "Convert character decisions and actions into structured events.\n\n"

        "Rules:\n"
        "- Split into atomic events\n"
        "- Use ONLY: thought, speech, action\n"
        "- Thoughts are ALWAYS to self\n"
        "- Be literal, do NOT infer beyond text\n\n"

        "Return STRICT JSON ARRAY of events:\n"
        "{\n"
        "  \"type\": \"thought|speech|action\",\n"
        "  \"actor\": \"string\",\n"
        "  \"target\": [\"string\"],\n"
        "  \"content\": \"string\",\n"
        "  \"metadata\": {\"intensity\": 0-100}\n"
        "}\n"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": npc_actions_text}
        ]
    )

    try:
        return json.loads(response.choices[0].message["content"])
    except:
        return []

def update_characters_from_output(story_output):
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

    prompt = (
        "You are an information extraction assistant.\n"
        "Given a story segment and the current character sheets, update only what has clearly changed.\n"
        "Use integers on a 0–100 scale for all strength/impact/value fields.\n"
        "Return STRICT JSON with this schema:\n\n"
        +character_information_extract_prompt()+
        "\n\nOnly include fields that actually changed.\n"
        "If nothing changed, return {\"characters\": {}}.\n"
    )

    payload = {
        "story_segment": story_output,
        "current_characters": chars
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
        updates = json.loads(content)
    except json.JSONDecodeError:
        return

    if "characters" not in updates:
        return

    for name, changes in updates["characters"].items():
        merge_character_changes(chars, name, changes)

    save_json(CHARACTERS_FILE, chars)

#------CHECK------

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

#------CHECK------
# and about order and classification
    
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

        "environment": {
            "weather": {"description": "", "severity": 0},
            "atmosphere": {
                "sensory": {"description": "", "value": 0},
                "emotional": {"description": "", "value": 0},
                "social": {"description": "", "value": 0}
            }
        },

        "narrative": {
            "objective": {"description": "", "priority": 0},
            "stakes": {"description": "", "severity": 0},
            "constraints": {}
        },

        "dynamics": {
            "danger_level": 0,
            "tension": 0
        },

        "characters_present": {},   # name -> {"focus": 0-100}
        "focus": {},                # name -> weight

        "objects": {},              # already good

        "conflicts": {},            # conflict_key -> {...}

        "events": {}                # event_key -> {...}
    }

def scene_information_extract_schema():
    return (
        "{\n"
        "  \"location\": {\n"
        "    \"key\": \"string\",\n"
        "    \"name\": \"string\",\n"
        "    \"description\": \"string\"\n"
        "  },\n"

        "  \"time\": {\n"
        "    \"time_of_day\": \"string\",\n"
        "    \"elapsed_hours\": \"number\"\n"
        "  },\n"

        "  \"environment\": {\n"
        "    \"weather\": {\"description\": \"string\", \"severity\": \"0-100\"},\n"
        "    \"atmosphere\": {\n"
        "      \"sensory\": {\"description\": \"string\", \"value\": \"0-100\"},\n"
        "      \"emotional\": {\"description\": \"string\", \"value\": \"0-100\"},\n"
        "      \"social\": {\"description\": \"string\", \"value\": \"0-100\"}\n"
        "    }\n"
        "  },\n"

        "  \"narrative\": {\n"
        "    \"objective\": {\"description\": \"string\", \"priority\": \"0-100\"},\n"
        "    \"stakes\": {\"description\": \"string\", \"severity\": \"0-100\"},\n"
        "    \"constraints\": {\"constraint_key\": \"string\"}\n"
        "  },\n"

        "  \"dynamics\": {\n"
        "    \"danger_level\": \"0-100\",\n"
        "    \"tension\": \"0-100\"\n"
        "  },\n"

        "  \"characters_present\": {\n"
        "    \"character_name\": {\"focus\": \"0-100\"}\n"
        "  },\n"

        "  \"focus\": {\n"
        "    \"character_name\": \"0-100\"\n"
        "  },\n"

        "  \"objects\": {\n"
        "    \"object_key\": {\n"
        "      \"name\": \"string\",\n"
        "      \"description\": \"string\",\n"
        "      \"state\": \"string\",\n"
        "      \"value\": \"0-100\",\n"
        "      \"owner\": \"string\"\n"
        "    }\n"
        "  },\n"

        "  \"conflicts\": {\n"
        "    \"conflict_key\": {\n"
        "      \"description\": \"string\",\n"
        "      \"parties\": {\"character\": \"0-100 involvement\"},\n"
        "      \"intensity\": \"0-100\",\n"
        "      \"status\": \"active/resolved\"\n"
        "    }\n"
        "  },\n"

        "  \"events\": {\n"
        "    \"event_key\": {\n"
        "      \"description\": \"string\",\n"
        "      \"impact\": \"0-100\"\n"
        "    }\n"
        "  }\n"
        "}"
    )

def update_scene_from_output(story_output):
    scene = load_json(SCENE_STATE_FILE, scene_template())
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

    prompt = prompt = (
        "You are an information extraction assistant.\n"
        "Given a story segment, current scene state, and known characters, "
        "update ONLY what has clearly changed or is newly implied.\n"
        "All numeric values are 0–100 integers unless stated otherwise.\n"
        "Return STRICT JSON with this schema (all fields optional):\n\n"
        +scene_information_extract_schema()+
        "\n\nDo NOT remove data unless explicitly resolved (e.g., conflict status = resolved)\n"
        "If nothing changed, return {}.\n"
    )

    payload = {
        "story_segment": story_output,
        "current_scene": scene,
        "characters": chars
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if not isinstance(updates, dict):
        return

    # 🔹 merge
    scene = deep_merge_dict(scene, updates)

    # 🔹 resolve conflicts
    if "conflicts" in updates:
        for k, v in updates["conflicts"].items():
            if isinstance(v, dict) and v.get("status") == "resolved":
                scene["conflicts"].pop(k, None)

    save_json(SCENE_STATE_FILE, scene)

# =========================
# GROQ CALL: WORLD UPDATES
# =========================
def world_template():
    return {
        "setting": "",
        "rules": {},
        "tone": {},
        "themes": {},

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

        "tags": {},

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

def world_information_extract_prompt():
    return (
        "{\n"
        "  \"factions\": {\n"
        "    \"faction_key\": {\n"
        "      \"name\": \"string\",\n"
        "      \"description\": \"string\",\n"
        "      \"rank\": \"string\",\n"
        "      \"type\": \"string\",\n"
        "      \"ideology\": \"string\",\n"
        "      \"goals\": {\"goal_key\": \"0-100\"},\n"
        "      \"influence\": \"0-100\",\n"
        "      \"resources\": {\"resource_key\": \"0-100\"},\n"
        "      \"territory\": {\"place_key\": {\"control\": \"0-100\"}},\n"
        "      \"leaders\": {\"character_name\": {\"role\": \"string\", \"influence\": \"0-100\"}},\n"
        "      \"relationships\": {\"faction_key\": \"-100 to 100\"}\n"
        "    }\n"
        "  },\n"
        "  \"important_places\": {\n"
        "    \"place_key\": {\n"
        "      \"name\": \"string\",\n"
        "      \"description\": \"string\",\n"
        "      \"atmosphere\": {\"description\": \"string\", \"value\": \"0-100\"},\n"
        "      \"tags\": {\"tag\": \"0-100\"},\n"
        "      \"faction_control\": {\"faction_key\": {\"control\": \"0-100\"}},\n"
        "      \"danger_level\": \"0-100\",\n"
        "      \"importance\": \"0-100\",\n"
        "      \"risk_profile\": {\n"
        "        \"natural\": {\"event\": \"0-100\"},\n"
        "        \"magical\": {\"event\": \"0-100\"},\n"
        "        \"political\": {\"event\": \"0-100\"}\n"
        "      }\n"
        "    }\n"
        "  },\n"
        "  \"important_events\": {\n"
        "    \"event_key\": {\n"
        "      \"description\": \"string\",\n"
        "      \"location\": \"place_key\",\n"
        "      \"factions_involved\": {\"faction_key\": \"0-100\"},\n"
        "      \"characters_involved\": {\"character_name\": \"0-100\"},\n"
        "      \"impact\": \"0-100\",\n"
        "      \"type\": \"string\",\n"
        "      \"status\": \"ongoing/resolved\"\n"
        "    }\n"
        "  }\n"
        "}"
    )

def merge_world_changes(world, updates):
    # ---------- FACTIONS ----------
    if "factions" in updates:
        for f_key, f_data in updates["factions"].items():
            if f_key not in world["factions"]:
                world["factions"][f_key] = faction_template()

            faction = world["factions"][f_key]

            # simple strings
            for field in ["name", "description", "rank", "type", "ideology"]:
                if field in f_data and isinstance(f_data[field], str):
                    faction[field] = f_data[field].strip()

            # influence
            if "influence" in f_data:
                faction["influence"] = clamp_int(f_data["influence"], 0, 100, 0)

            # goals/resources
            for field in ["goals", "resources"]:
                if field in f_data and isinstance(f_data[field], dict):
                    if field not in faction:
                        faction[field] = {}
                    for k, v in f_data[field].items():
                        faction[field][k] = clamp_int(v, 0, 100, 0)

            # territory
            if "territory" in f_data:
                for place, pdata in f_data["territory"].items():
                    if place not in faction["territory"]:
                        faction["territory"][place] = {"control": 0}
                    if "control" in pdata:
                        faction["territory"][place]["control"] = clamp_int(pdata["control"], 0, 100, 0)

            # leaders
            if "leaders" in f_data:
                for name, ldata in f_data["leaders"].items():
                    if name not in faction["leaders"]:
                        faction["leaders"][name] = {"role": "", "influence": 0}
                    if "role" in ldata:
                        faction["leaders"][name]["role"] = ldata["role"]
                    if "influence" in ldata:
                        faction["leaders"][name]["influence"] = clamp_int(ldata["influence"], 0, 100, 0)

            # relationships
            if "relationships" in f_data:
                for other, val in f_data["relationships"].items():
                    faction["relationships"][other] = clamp_int(val, -100, 100, 0)

    # ---------- PLACES ----------
    if "important_places" in updates:
        for p_key, p_data in updates["important_places"].items():
            if p_key not in world["important_places"]:
                world["important_places"][p_key] = place_template()

            place = world["important_places"][p_key]

            for field in ["name", "description"]:
                if field in p_data:
                    place[field] = p_data[field]

            if "danger_level" in p_data:
                place["danger_level"] = clamp_int(p_data["danger_level"], 0, 100, 0)

            if "importance" in p_data:
                place["importance"] = clamp_int(p_data["importance"], 0, 100, 0)

            # faction control
            if "faction_control" in p_data:
                for f, fdata in p_data["faction_control"].items():
                    if f not in place["faction_control"]:
                        place["faction_control"][f] = {"control": 0}
                    place["faction_control"][f]["control"] = clamp_int(fdata["control"], 0, 100, 0)

    # ---------- EVENTS ----------
    if "important_events" in updates:
        for e_key, e_data in updates["important_events"].items():
            if e_key not in world["important_events"]:
                world["important_events"][e_key] = event_template()

            event = world["important_events"][e_key]

            for field in ["description", "location", "type", "status"]:
                if field in e_data:
                    event[field] = e_data[field]

            if "impact" in e_data:
                event["impact"] = clamp_int(e_data["impact"], 0, 100, 0)

            # factions involved
            if "factions_involved" in e_data:
                for f, val in e_data["factions_involved"].items():
                    event["factions_involved"][f] = clamp_int(val, 0, 100, 0)

            # characters involved
            if "characters_involved" in e_data:
                for c, val in e_data["characters_involved"].items():
                    event["characters_involved"][c] = clamp_int(val, 0, 100, 0)

    return world

def update_world_from_output(story_output):
    world = load_json(WORLD_BIBLE_FILE, world_template())

    prompt = (
        "You are an information extraction assistant.\n"
        "Extract NEW or UPDATED world information.\n"
        "Return STRICT JSON:\n\n"
        +world_information_extract_prompt()+
        "\n\nIf nothing changed, return {}."
    )

    payload = {
        "story_segment": story_output,
        "current_world": world
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
        ]
    )

    try:
        updates = json.loads(response.choices[0].message["content"])
    except:
        return

    if not isinstance(updates, dict):
        return

    world = merge_world_changes(world, updates)
    save_json(WORLD_BIBLE_FILE, world)

# #------Messy Ideas: save for later bin------
# def generate_random_world_event():
#     world = load_json(WORLD_BIBLE_FILE, {})
#     scene = load_json(SCENE_STATE_FILE, {})

#     place_key = scene.get("location_key", "")
#     if not place_key:
#         return None

#     place = world.get("important_places", {}).get(place_key, {})
#     if not place:
#         return None

#     natural = place.get("natural_risk_profile", {})
#     magical = place.get("magical_risk_profile", {})
#     political = place.get("political_risk_profile", {})

#     all_risks = {**natural, **magical, **political}
#     if not all_risks:
#         return None

#     total_weight = sum(all_risks.values())
#     if total_weight <= 0:
#         return None

#     roll = random.uniform(0, total_weight)
#     cumulative = 0
#     for event_type, weight in all_risks.items():
#         cumulative += weight
#         if roll <= cumulative:
#             return event_type

#     return None

# def npc_autonomous_drift():
#     """
#     Let the model propose small, plausible off-screen updates:
#     - character drift (personality, goals, relationships, roles, abilities, states)
#     - new or updated ongoing_projects
#     - new important_events / important_places / factions if they arise
#     """
#     world = load_json(WORLD_BIBLE_FILE, {})
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     scene = load_json(SCENE_STATE_FILE, {})
#     short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
#     medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
#     long_summary = load_text(LONG_SUMMARY_FILE, "")

#     prompt = (
#         "You are an assistant simulating off-screen NPC evolution in a narrative world.\n\n"
#         "Given:\n"
#         "- all character sheets,\n"
#         "- the world bible (including factions, places, rules, and ongoing_projects),\n"
#         "- the current scene,\n"
#         "- short/medium memory,\n"
#         "- and the long-term summary,\n\n"
#         "propose SMALL, PLAUSIBLE updates that reflect how NPCs and the world evolve over time.\n\n"
#         "Consider:\n"
#         "- personality drift (traits strengthen or weaken based on events, stress, success, trauma)\n"
#         "- relationship drift (trust, resentment, affection, rivalry)\n"
#         "- goal evolution (new goals, abandoned goals, shifting priorities)\n"
#         "- role evolution (roles strengthen or weaken based on actions, abilities, background, species)\n"
#         "- ability evolution (training, practice, injury, decay, species effects)\n"
#         "- physical_state drift (fatigue, healing, injury progression, sickness)\n"
#         "- mental_state drift (stress, fear, depression, confidence)\n"
#         "- appearance drift (haircuts, scars, aging, clothing changes)\n"
#         "- background updates (major events become part of life history)\n"
#         "- time passed (scene.time_elapsed_total_hours)\n"
#         "- ongoing_projects (training, healing, construction, travel)\n"
#         "- world rules (e.g., if a rule disables an ability after killing, set that ability to 0)\n"
#         "- random but plausible events based on species, personality, state, and risk profiles\n"
#         "- highly charismatic characters may attract new acquaintances or followers\n\n"
#         "- world rules and settings almost never change; they change only under extraordinary circumstances.\n"
#         "- Only NPCs with exceptional power, influence, magical ability, political authority, or destiny may alter rules or settings.\n"
#         "- Rule or setting changes require strong justification from recent events, long-term memory, and the character’s sheet.\n"
#         "- These changes should be extremely rare and only occur when the narrative strongly supports them.\n"
#         "NPCs may introduce new characters, new important_places, new factions, and new important_events when appropriate.\n"
#         "NPCs do NOT see numeric world values; they infer danger and opportunity from descriptions and their own biases.\n\n"
#         "Respect continuity:\n"
#         "- emotional states persist unless something changes them.\n"
#         "- grudges and bonds do not vanish.\n"
#         "- long-term projects continue unless interrupted.\n"
#         "- injuries heal slowly unless treated.\n"
#         "- depression does not vanish without cause.\n\n"
#         "Return STRICT JSON:\n"
#         "{\n"
#         "  \"characters\": {\n"
#         "    \"Name\": { ... updated fields ... }\n"
#         "  },\n"
#         "  \"ongoing_projects\": {\n"
#         "    \"project_key\": { ... updated or new project ... }\n"
#         "  },\n"
#         "  \"world_updates\": {\n"
#         "    \"important_places\": { ... new or updated places ... },\n"
#         "    \"factions\": { ... new or updated factions ... },\n"
#         "    \"important_events\": [ ... new events ... ]\n"
#         "  }\n"
#         "}\n"
#     )

#     payload = {
#         "world_bible": world,
#         "characters": chars,
#         "scene_state": scene,
#         "short_memory": short_mem,
#         "medium_memory": medium_mem,
#         "long_summary": long_summary
#     }

#     response = client.chat.completions.create(
#         model=MODEL,
#         messages=[
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
#         ]
#     )

#     content = response.choices[0].message["content"]
#     try:
#         updates = json.loads(content)
#     except json.JSONDecodeError:
#         return

#     # Merge character updates using the same semantics as update_characters_from_output
#     if "characters" in updates and isinstance(updates["characters"], dict):
#         if "characters" not in chars or not isinstance(chars["characters"], dict):
#             chars["characters"] = {}
#         for name, changes in updates["characters"].items():
#             merge_character_changes(chars, name, changes)
#         save_json(CHARACTERS_FILE, chars)

#     # Merge ongoing_projects safely
#     if "ongoing_projects" in updates and isinstance(updates["ongoing_projects"], dict):
#         world.setdefault("ongoing_projects", {})

#         for key, proj in updates["ongoing_projects"].items():
#             if key in world["ongoing_projects"]:
#                 deep_merge_dict(world["ongoing_projects"][key], proj)
#             else:
#                 world["ongoing_projects"][key] = proj

#     # Merge world_updates safely
#     world_updates = updates.get("world_updates", {})

#     # Ensure base structures exist
#     world.setdefault("important_places", {})
#     world.setdefault("factions", {})
#     world.setdefault("important_events", [])

#     # Important places
#     if isinstance(world_updates.get("important_places"), dict):
#         for p_key, p_val in world_updates["important_places"].items():
#             if p_key in world["important_places"]:
#                 deep_merge_dict(world["important_places"][p_key], p_val)
#             else:
#                 world["important_places"][p_key] = p_val

#     # Factions
#     if isinstance(world_updates.get("factions"), dict):
#         for f_key, f_val in world_updates["factions"].items():
#             if f_key in world["factions"]:
#                 deep_merge_dict(world["factions"][f_key], f_val)
#             else:
#                 world["factions"][f_key] = f_val

#     # Important events
#     if isinstance(world_updates.get("important_events"), list):
#         for ev in world_updates["important_events"]:
#             if ev not in world["important_events"]:
#                 world["important_events"].append(ev)

#     save_json(WORLD_BIBLE_FILE, world)

# def start_training_project(character_name, skill, estimated_hours):
#     world = load_json(WORLD_BIBLE_FILE, {})
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})

#     if character_name not in chars.get("characters", {}):
#         return

#     key = f"{character_name.lower()}_{skill.lower()}_training"

#     world.setdefault("ongoing_projects", {})
#     world["ongoing_projects"][key] = {
#         "description": f"{character_name} is training {skill}.",
#         "type": "training",
#         "owner": character_name,
#         "skill_target": skill,
#         "started_at_hours": 0,
#         "progress_hours": 0,
#         "estimated_total_hours": estimated_hours,
#         "status": "in_progress"
#     }

#     save_json(WORLD_BIBLE_FILE, world)

# def advance_projects_by_time():
#     """
#     Let the model advance ongoing_projects based on time, personality, state, and memory.
#     """
#     world = load_json(WORLD_BIBLE_FILE, {})
#     scene = load_json(SCENE_STATE_FILE, {})
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
#     medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
#     long_summary = load_text(LONG_SUMMARY_FILE, "")

#     hours = scene.get("last_segment_hours", 0)
#     if hours <= 0:
#         return

#     projects = world.get("ongoing_projects", {})

#     prompt = (
#         "You are an assistant that advances ongoing projects over time.\n"
#         "Given characters, ongoing_projects, time passed (in hours), and story memory, update:\n"
#         "- project.progress_hours\n"
#         "- project.status (in_progress/completed/abandoned)\n"
#         "Training projects should progress based on personality, abilities, physical/mental state, and consistency.\n"
#         "Some characters may stall or abandon projects; others persist.\n"
#         "Return STRICT JSON: {\"ongoing_projects\": {\"key\": { ...updated project... }}}\n"
#     )

#     payload = {
#         "characters": chars,
#         "ongoing_projects": projects,
#         "hours_passed": hours,
#         "short_memory": short_mem,
#         "medium_memory": medium_mem,
#         "long_summary": long_summary
#     }

#     response = client.chat.completions.create(
#         model=MODEL,
#         messages=[
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
#         ]
#     )

#     content = response.choices[0].message["content"]
#     try:
#         updates = json.loads(content)
#     except json.JSONDecodeError:
#         return

#     if "ongoing_projects" in updates and isinstance(updates["ongoing_projects"], dict):
#         for proj_key, proj_val in updates.get("ongoing_projects", {}).items():
#             if proj_key in world["ongoing_projects"]:
#                 deep_merge_dict(world["ongoing_projects"][proj_key], proj_val)
#             else:
#                 world["ongoing_projects"][proj_key] = proj_val
#         save_json(WORLD_BIBLE_FILE, world)

# def apply_completed_projects():
#     world = load_json(WORLD_BIBLE_FILE, {})
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})

#     projects = world.get("ongoing_projects", {})

#     for key, proj in list(projects.items()):
#         if proj.get("status") != "completed":
#             continue

#         owner = proj.get("owner")
#         if owner not in chars.get("characters", {}):
#             continue

#         char = chars["characters"][owner]

#         if proj["type"] == "training":
#             skill = proj["skill_target"]
#             char.setdefault("abilities", {})
#             old_val = char["abilities"].get(skill, 0)
#             char["abilities"][skill] = min(100, old_val + 5)

#             # Add to background
#             char.setdefault("background", {})
#             char["background"][f"{skill}_training_completed"] = {
#                 "description": f"Completed training in {skill}.",
#                 "impact": 50
#             }

#         # Remove project
#         del projects[key]

#     save_json(CHARACTERS_FILE, chars)
#     save_json(WORLD_BIBLE_FILE, world)

# def apply_role_evolution():
#     """
#     Let the model infer how roles evolve based on abilities, background, and events.
#     """
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     long_summary = load_text(LONG_SUMMARY_FILE, "")

#     prompt = (
#         "You are an assistant that updates characters' roles over time.\n"
#         "Given character sheets and the long-term summary, adjust their 'role' weights to reflect who they are now.\n"
#         "Consider:\n"
#         "- abilities and skills\n"
#         "- background events\n"
#         "- goals and recent activities\n"
#         "Return STRICT JSON: {\"characters\": {\"Name\": {\"role\": {\"role_key\": int}}}}\n"
#     )

#     payload = {
#         "characters": chars,
#         "long_summary": long_summary
#     }

#     response = client.chat.completions.create(
#         model=MODEL,
#         messages=[
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
#         ]
#     )

#     content = response.choices[0].message["content"]
#     try:
#         updates = json.loads(content)
#     except json.JSONDecodeError:
#         return

#     if "characters" not in updates:
#         return

#     for name, changes in updates["characters"].items():
#         if name not in chars["characters"]:
#             continue
#         char = chars["characters"][name]
#         if "role" in changes and isinstance(changes["role"], dict):
#             if "role" not in char or not isinstance(char["role"], dict):
#                 char["role"] = {}
#             for k, v in changes["role"].items():
#                 char["role"][k] = v

#     save_json(CHARACTERS_FILE, chars)

# def update_background_from_events():
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     long_summary = load_text(LONG_SUMMARY_FILE, "")

#     for name, char in chars.get("characters", {}).items():
#         if name in long_summary:
#             char.setdefault("background", {})
#             char["background"][f"long_term_event_{len(char['background'])}"] = {
#                 "description": f"Referenced in long-term summary: {name}",
#                 "impact": 20
#             }

#     save_json(CHARACTERS_FILE, chars)
    
# def apply_state_drift():
#     """
#     Let the model infer how physical_state and mental_state drift over time,
#     based on species, aging_rate, immortality, personality, abilities, and memory.
#     """
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
#     medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
#     long_summary = load_text(LONG_SUMMARY_FILE, "")

#     prompt = (
#         "You are an assistant that updates characters' physical and mental states over time.\n"
#         "Given character sheets and story memory, infer how their physical_state and mental_state drift:\n"
#         "- Immortal or slow-aging species maintain physical stability unless injured.\n"
#         "- Some states persist (e.g., depression) if nothing changes.\n"
#         "- Some states recover slowly (fatigue, mild stress) if time passes peacefully.\n"
#         "- Some states worsen if long-term stress, trauma, or unresolved conflict persists.\n"
#         "- Species and aging_rate influence recovery and decay.\n"
#         "- Low health or harsh conditions may cause sickness or further decline.\n"
#         "Do NOT reset emotions or injuries without reason.\n"
#         "Return STRICT JSON: {\"characters\": {\"Name\": {\"physical_state\": {...}, \"mental_state\": {...}}}}\n"
#     )

#     payload = {
#         "characters": chars,
#         "short_memory": short_mem,
#         "medium_memory": medium_mem,
#         "long_summary": long_summary
#     }

#     response = client.chat.completions.create(
#         model=MODEL,
#         messages=[
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}
#         ]
#     )

#     content = response.choices[0].message["content"]
#     try:
#         updates = json.loads(content)
#     except json.JSONDecodeError:
#         return

#     if "characters" not in updates:
#         return

#     for name, changes in updates["characters"].items():
#         if name not in chars["characters"]:
#             continue
#         char = chars["characters"][name]

#         for field in ["physical_state", "mental_state"]:
#             if field in changes and isinstance(changes[field], dict):
#                 if field not in char or not isinstance(char[field], dict):
#                     char[field] = {}
#                 for key, val in changes[field].items():
#                     if key not in char[field]:
#                         char[field][key] = {"description": "", "value": 0}
#                     if "description" in val:
#                         char[field][key]["description"] = val["description"]
#                     if "value" in val:
#                         char[field][key]["value"] = val["value"]

#     save_json(CHARACTERS_FILE, chars)

# def apply_character_aging():
#     """
#     Update age_actual and age_apparent for all characters based on
#     scene.time_elapsed_total_hours, species, aging_rate, and immortality.
#     """
#     chars = load_json(CHARACTERS_FILE, {"characters": {}})
#     scene = load_json(SCENE_STATE_FILE, {})

#     total_hours = scene.get("time_elapsed_total_hours", 0)
#     if total_hours <= 0:
#         return

#     years_passed = total_hours / 8760.0  # 8760 hours in a year

#     for name, char in chars.get("characters", {}).items():
#         # Immortal: actual age grows, apparent age stays fixed
#         if char.get("is_immortal", False):
#             if isinstance(char.get("age_actual"), (int, float)):
#                 char["age_actual"] = char["age_actual"] + years_passed
#             continue

#         aging_rate = char.get("aging_rate", 1.0)

#         # Actual age
#         if isinstance(char.get("age_actual"), (int, float)):
#             char["age_actual"] = char["age_actual"] + years_passed * aging_rate

#         # Apparent age (slightly slower)
#         if isinstance(char.get("age_apparent"), (int, float)):
#             char["age_apparent"] = char["age_apparent"] + years_passed * aging_rate * 0.7

#     save_json(CHARACTERS_FILE, chars)
# #------Messy Ideas: save for later bin------

# =========================
# MAIN LOOP
# =========================
def main():
    init_files()
    memory_manager = MemoryManager()
    turn_counter = 0

    print("Roleplay story engine ready.")
    print("You are the player character. Describe and direct the player character in *third* person.")
    print("Type 'exit' to quit.\n")

    while True:
        player_action = input("actions or words: ").strip()
        if player_action.lower() == "exit":
            break

        # 1. Detect if the player is describing a new character
        detect_and_create_character_from_input(player_action)

        # 2. Load updated characters, scene, and player name
        chars = load_json(CHARACTERS_FILE, {"characters": {}}).get("characters", {})
        scene = load_json(SCENE_STATE_FILE, {})
        player = load_json(PLAYER_FILE, {"player_character": ""})
        player_name = player.get("player_character", "").strip()

        # # 3. Optional random world event injected into the input
        # random_event = generate_random_world_event()
        # if random_event:
        #     player_action += f"\n\n[WORLD EVENT OCCURS: {random_event}]"

        # 4. NPC decision-making BEFORE story generation
        npc_actions = []
        for npc in scene.get("characters_present", []):
            if npc not in chars:
                continue
            if npc == player_name:
                continue  # skip player

            decision = decide_character_action(
                npc,
                f"Current scene: {scene}. Recent events: {load_text(CHAPTER_LOG_FILE)}"
            )
            npc_actions.append(f"{npc}: {decision}")

        # 5. Combine player + NPC actions into one input
        combined_actions = player_action
        if npc_actions:
            combined_actions += "\n\nNPC Actions:\n" + "\n".join(npc_actions)
        # ------------------------
        # 2. Extract events (NEW)
        # ------------------------
        raw_events = extract_events_from_decisions(combined_actions)

        events = []
        for raw in raw_events:
            e = normalize_and_validate_event(raw)
            if e:
                events.append(e)
        # ------------------------
        # 3. Build perception (NEW)
        # ------------------------
        perception = build_perception(events, scene)
        # ------------------------
        # 4. Update characters (NEW CORE SYSTEM)
        # ------------------------
        for char_name, perceived in perception.items():
            update_character_from_perception(char_name, perceived)
        # ------------------------
        # 5. THEN generate story
        # ------------------------
        story_output = generate_story(combined_actions)

        print("\n--- Story Output ---\n")
        print(story_output)
        print("\n--------------------\n")

        # 7. Log story output
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_text(CHAPTER_LOG_FILE, f"[{timestamp}] CHAPTER:\n{story_output}\n")

        # 8. Estimate time passage and update scene time
        hours = estimate_time_passage(story_output)
        scene = load_json(SCENE_STATE_FILE, {})
        scene["last_segment_hours"] = hours
        scene["time_elapsed_total_hours"] = scene.get("time_elapsed_total_hours", 0) + hours
        save_json(SCENE_STATE_FILE, scene)

        # 9. Auto-update world, characters, scene from explicit text
        # update_characters_from_output(story_output)
        update_scene_from_output(story_output)
        update_world_from_output(story_output)

        # 10. Summarize and update memory
        summary = summarize_output_for_memory(story_output)
        memory_manager.add_event_summary(summary)

        # # 11. Systemic simulation updates (model-driven)
        # apply_character_aging()      # species + aging_rate + immortality
        # apply_state_drift()          # physical/mental drift, sickness, recovery, etc.
        # advance_projects_by_time()   # training/construction/healing/travel progress (upgrade this to be model-aware)
        # apply_completed_projects()   # apply finished project effects
        # apply_role_evolution()       # roles drifting based on actions (model-driven if you wired it that way)
        # update_background_from_events()  # major events → background entries

        # # 12. Off-screen NPC/world evolution (small, plausible drifts + new entities)
        # turn_counter += 1
        # if turn_counter % 3 == 0:
        #     npc_autonomous_drift()


if __name__ == "__main__":
    main()
