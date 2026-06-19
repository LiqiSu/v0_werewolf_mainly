import os
import json
import getpass
import re
import uuid
from datetime import datetime
from groq import Groq
import random
import copy
import traceback
import time
import difflib
import math

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    API_KEY = getpass.getpass("GROQ API key: ").strip()

MODEL_LARGE = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]
MODEL_SMALL = ["openai/gpt-oss-20b", "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant", "qwen/qwen3-32b"]

DATA_DIR = "data"
WORLD_BIBLE_FILE = os.path.join(DATA_DIR, "world_bible.json")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.json")
SCENE_STATE_FILE = os.path.join(DATA_DIR, "scene_state.json")
GAME_ROUNDS_FILE = os.path.join(DATA_DIR, "game_rounds.json")
CHARACTERS_PROFILE_FILE = os.path.join(DATA_DIR, "characters_profile.json")

STYLE_GUIDE_FILE = os.path.join(DATA_DIR, "style_guide.txt")
PLAYER_FILE = os.path.join(DATA_DIR, "player.json")

EVENT_LOG_FILE = os.path.join(DATA_DIR, "event_log.txt")

os.makedirs(DATA_DIR, exist_ok=True)

client = Groq(api_key=API_KEY)

# LOGGING ISSUE:
    # try-except error logging
    # some don't have try-except
# LLM OUTPUT NORMALIZING ISSUE:
    # only minimal normalization
    # largely relying on LLM to output the correct format/structure
    # low error tolerance regarding LLM no behaving
# high entropy:
    # only minimal memory management
    # almost no knowledge crystalization/management
    # prone to drift/corrupt/crash overtime (too much noisy/not pruned input)
# global variables issue...
# needs refactoring. certainly.
# be aware of keys/names/potential replacement/not found issues. uuid...? (maybe later)

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
# LOGGING HELPERS
# =========================
# logging system: not "done" yet. also, the except is pass
PUBLIC_LOG_FILE = "public_log.txt"
DEBUG_LOG_FILE = "debug_log.txt"
LLM_LOG_FILE = "llm_log.txt"
LLM_FILTER_FILE = "llm_filter_log.txt"

def _stamp():
    return datetime.now().strftime("%H:%M:%S")

def _append(filename, text):
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except:
        pass

def log_error(context, e):
    line = f"[{_stamp()}] [ERROR] {context}: {str(e)}"
    print(line)
    _append(DEBUG_LOG_FILE, line)
    try:
        _append(DEBUG_LOG_FILE, traceback.format_exc())
    except:
        pass

def log_llm(msg, file_type="llm"):
    if file_type == "llm":
        _append(LLM_LOG_FILE, msg)
    if file_type == "llm_filter":
        _append(LLM_FILTER_FILE, msg)

def log_llm_interaction(actor, action_type, prompt_data, raw_output, parsed_output, file_type = "llm"):
    log_llm("", file_type)
    log_llm("==============================", file_type)
    log_llm(f"[{_stamp()}]", file_type)
    log_llm(f"ACTOR: {actor}", file_type)
    log_llm(f"ACTION: {action_type}", file_type)

    log_llm("", file_type)
    log_llm("--- PROMPT ---", file_type)
    try:
        log_llm(json.dumps(prompt_data, indent=2, ensure_ascii=False), file_type)
    except:
        log_llm(str(prompt_data), file_type)

    log_llm("", file_type)
    log_llm("--- RAW OUTPUT ---", file_type)
    log_llm(str(raw_output), file_type)

    log_llm("", file_type)
    log_llm("--- PARSED ---", file_type)
    try:
        log_llm(json.dumps(parsed_output, indent=2, ensure_ascii=False), file_type)
    except:
        log_llm(str(parsed_output), file_type)

    log_llm("==============================", file_type)
    log_llm("", file_type)

# public messages only
def public_event(msg):
    line = f"[{_stamp()}] {msg}"
    print(line)
    _append(PUBLIC_LOG_FILE, line)

# hidden engine info
def private_event(msg):
    line = f"[{_stamp()}] {msg}"
    _append(DEBUG_LOG_FILE, line)
        
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
    
    if not os.path.exists(CHARACTERS_PROFILE_FILE):
        save_json(CHARACTERS_PROFILE_FILE, {"characters": {}})

    if not os.path.exists(SCENE_STATE_FILE):
        save_json(SCENE_STATE_FILE, {})
    
    if not os.path.exists(GAME_ROUNDS_FILE):
        save_json(GAME_ROUNDS_FILE, {})

    if not os.path.exists(STYLE_GUIDE_FILE):
        save_text(STYLE_GUIDE_FILE, "")

    if not os.path.exists(PLAYER_FILE):
        save_json(PLAYER_FILE, {"player_character": ""})

    if not os.path.exists(EVENT_LOG_FILE):
        save_text(EVENT_LOG_FILE, "")
    
    if not os.path.exists(PUBLIC_LOG_FILE):
        save_text(PUBLIC_LOG_FILE, "")
    
    if not os.path.exists(DEBUG_LOG_FILE):
        save_text(DEBUG_LOG_FILE, "")

    if not os.path.exists(LLM_LOG_FILE):
        save_text(LLM_LOG_FILE, "")
    
    if not os.path.exists(LLM_FILTER_FILE):
        save_text(LLM_FILTER_FILE, "")

# =========================
# LLM NORMALIZER
# =========================
# ummm...didn't use fuzzy match even inside of key/answer...can consider
def normalize_answer(raw_answer, valid_options=None, default_answer="pass"):
    if raw_answer is None:
        return default_answer

    txt = str(raw_answer).strip()

    if not txt:
        return default_answer

    # first line only
    txt = txt.splitlines()[0].strip()

    # remove punctuation edges
    txt = txt.strip(" .,!?:;\"'`()[]{}")

    if not valid_options:
        return txt

    # exact case-insensitive match first
    for opt in valid_options:
        if txt.lower() == str(opt).lower():
            return opt

    # contains exact token
    for opt in valid_options:
        pattern = r'\b' + re.escape(str(opt)) + r'\b'
        if re.search(pattern, txt, re.I):
            return opt

    return default_answer

# -------------------------------------------------
# semantic block parser
# used AFTER normal parsing
# -------------------------------------------------
# a bit too aggressive (ditching...?)
def normalize_semantic_entries(entries, allowed_verbs, valid_names,
    max_lines=3, max_content_words=6
):
    """
    Input:
        list[str]

    Example input:
        [
            "suspect|AA|fake claim",
            "trust|GA|consistent"
        ]

    Returns:
        cleaned list[str]
    """

    if not entries:
        return []

    valid_names += (["self"] + ["all"])

    out = []
    seen = set()
    for raw in entries:
        if not raw:
            continue

        line = str(raw).strip().lower()

        if not line:
            continue

        # normalize separators/spaces
        line = re.sub(r'\s*\|\s*', '|', line)
        line = re.sub(r'\s+', ' ', line)
        parts = line.split("|")

        # must be have at least verb|target
        if len(parts) < 2:
            continue
        
        for i in range(len(parts)):
            if(i == 0):
                verb = parts[0].strip()
            elif(i == 1):
                target = parts[1].strip()
            elif(i == 2):
                content = parts[2].strip()
            else:
                break
    
        # -------------------------
        # verb validation
        # -------------------------
        if verb not in allowed_verbs:
            continue

        # -------------------------
        # target validation
        # -------------------------
        target = target.upper()
        if target not in valid_names:
            continue

        # -------------------------
        # content validation
        # -------------------------
        content = content.strip()
        if not content:
            content = ""

        # prevent runaway output
        if len(content.split()) > max_content_words:
            content = ""

        normalized = f"{verb}|{target}|{content}"

        low = normalized.lower()
        if low in seen:
            continue

        seen.add(low)
        out.append(normalized)

        if len(out) >= max_lines:
            break

    return out

def parse_llm_output(raw_text, mode="speak", valid_options=None,
    default_speech=[], default_answer="pass"
):
    """
    Modes:
    - speak
    - answer
    - summary
    - signals

    Returned:
    {
        "speech": [ ... ],
        "internal_reasoning": [ ... ]
    }
    """

    if raw_text is None:
        raw_text = ""

    text = str(raw_text).strip()

    # -------------------------------------------------
    # aliases
    # -------------------------------------------------
    key_alias = {
        "internal_reasoning": [
            "internal_reasoning", "internal reasoning",
            "reasoning", "thoughts", "logic", "analysis"
        ],

        "speech": [
            "speech", "say", "statement",
            "message", "talk"
        ],

        "answer": [
            "answer", "vote", "choice",
            "decision", "selection", "target"
        ],

        "summary": [
            "summary", "summarize", "compressed",
            "short summary", "brief summary"
        ],

       "signals": [
            "signals", "signal",
            "useful signals", "memory signals",
            "strategic signals"
        ]
    }

    # -------------------------------------------------
    # normalize label
    # -------------------------------------------------
    def normalize_label(label):
        s = str(label).lower().strip()
        s = re.sub(r'[^a-z_ ]', '', s)
        s = re.sub(r'\s+', ' ', s)
        for canon, aliases in key_alias.items():
            if s in aliases:
                return canon

        return None

    # -------------------------------------------------
    # cleanup
    # -------------------------------------------------
    def clean(v):
        v = str(v).replace("```", "")
        return v.strip()

    # -------------------------------------------------
    # normalize structured lines
    # -------------------------------------------------
    def normalize_structured_block(v):
        """
        Returns list[str]
        """

        v = clean(v)

        if not v:
            return []

        if v.upper() == "DROP":
            return []

        # split
        parts = re.split(r'[\n]+', v)

        out = []
        seen = set()
        for p in parts:
            p = p.strip()

            if not p:
                continue

            # normalize spaces around |
            p = re.sub(r'\s*\|\s*', '|', p)
            p = re.sub(r'\s+', ' ', p)
            low = p.lower()

            if low in seen:
                continue

            seen.add(low)
            out.append(p)

        return out

    # -------------------------------------------------
    # defaults
    # -------------------------------------------------
    if mode == "speak":
        result = {
            "speech": [],
            "internal_reasoning": []
        }

    elif mode == "answer":
        result = {
            "internal_reasoning": [],
            "answer": default_answer
        }

    elif mode == "summary":
        result = {"summary": ""}

    elif mode == "signals":
        result = {"signals": []}

    else:
        result = {}

    # =================================================
    # STAGE 1
    # label:
    # <<<
    # content
    # >>>
    # =================================================
    marker_pattern = re.compile(
        r'(?ims)^\s*([A-Za-z_ ]{2,40})\s*:\s*\n?\s*<<<\s*\n?(.*?)\n?\s*>>>'
    )

    found = marker_pattern.findall(text)
    if found:
        parsed_any = False

        for raw_label, raw_content in found:
            key = normalize_label(raw_label)

            if not key:
                continue

            val = clean(raw_content)

            # -----------------------------------------
            # structured list modes
            # -----------------------------------------
            if key in ["speech", "internal_reasoning", "signals"]:
                val = normalize_structured_block(val)

            if val:
                result[key] = val
                parsed_any = True

        if parsed_any:
            if mode == "answer":
                result["answer"] = normalize_answer(
                    result.get("answer", default_answer),
                    valid_options, default_answer
                )

            return result

    # =================================================
    # STAGE 2
    # label:
    # multiline without >>>
    # =================================================
    lines = text.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^\s*([A-Za-z_ ]{2,40})\s*:\s*$', line)

        if not m:
            i += 1
            continue

        key = normalize_label(m.group(1))

        if not key:
            i += 1
            continue

        collected = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()

            if not nxt:
                j += 1
                continue

            # next label begins
            if re.match(r'^[A-Za-z_ ]{2,40}\s*:', nxt):
                break

            if nxt == "<<<" or nxt == ">>>":
                j += 1
                continue

            collected.append(nxt)
            j += 1

        raw_val = "\n".join(collected).strip()

        if key in ["speech", "internal_reasoning", "signals"]:
            val = normalize_structured_block(raw_val)
        else:
            val = clean(raw_val)

        if val:
            result[key] = val

        i = j

    # =================================================
    # STAGE 3
    # one-line fallback
    # speech: xxx
    # =================================================
    for line in lines:
        m = re.match(r'^\s*([A-Za-z_ ]{2,40})\s*:\s*(.+?)\s*$', line)

        if not m:
            continue

        key = normalize_label(m.group(1))

        if not key:
            continue

        raw_val = clean(m.group(2))

        if key in ["speech", "internal_reasoning", "signals"]:
            val = normalize_structured_block(raw_val)
        else:
            val = raw_val

        if val:
            result[key] = val

    if mode == "answer":
        result["answer"] = normalize_answer(
            result.get("answer", default_answer),
            valid_options, default_answer
        )

    return result

# =========================
# ESTIMATE IN-WORLD TIME PASSAGE
# =========================
# NOT USED CURRENTLY
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
# CHARACTERS
# =========================
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

        "goals": {},
        "traits": {},
        "interests": {},
        "dislikes": {},

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
            "is_dead": {"value": False, "confidence": 0}
        }
    }

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
            "objects": {},
            "rules": {},
            "dynamics": {
                "danger_level": 0,
                "tension": 0
            },
            "characters_present": {},
            "conflicts": {},
            "events": {}
        },

        "hard_knowledge": {}
    }

def character_template():
    return {
        "name": "",
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

        "goals": {},
        "properties": {},
        "personality": {},
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
            "is_dead": False
        }
    }
    
# =========================
# SCENE
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

        "characters_present": {},

        "environment": {},
        "objects": {},

        "rules": {},

        "dynamics": {
            "danger_level": 0,
            "tension": 0
        },

        "conflicts": {},       
        "events": {}
    }

# =========================
# WORLD SECT - FOR NOW
# =========================
def world_template():
    return {
        "setting": "",
        "rules": {},

        "factions": {},
        "cultures": {},
        "important_places": {},
        "important_events": {}
    }

# =========================
# INITIALIZING GAME STATE
# =========================
def game_round_template():
    return {
        "current_round": 0,
        "current_phase_step": "",
        "living_players": [],
        "living_roles": [],
        "game_status": "ongoing"
    }

def game_rule(player_number, roles):
    # -------------------------------------------------
    # Parse role names
    # -------------------------------------------------
    role_names = []
    for item in roles.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(" ", 1)
        if len(parts) == 2:
            role_names.append(parts[1].strip().lower())
        else:
            role_names.append(parts[0].strip().lower())
    # helper
    def has(role):
        return role.lower() in role_names

    # ----------------------------
    # role mechanics
    # ----------------------------
    mech = []
    save = []
    if has("werewolf") or has("werewolves"):
        mech.append("Werewolves: private discuss then vote 1 night kill target; can choose no_kill or self-kill; tie=no_kill.")

    if has("seer"):
        mech.append("Seer: inspect 1 player nightly; learns team only.")

    if has("guardian angel"):
        mech.append("Guardian Angel: protect 1 player nightly; no same player twice in a row; blocks wolf kill only.")
        save.append("guardian angel protected right")

    if has("witch"):
        mech.append("Witch: 2 potions in the entire game; 1 save potion cancels 1 wolf kill (witch can KNOW wolf's target if still have save potion), 1 poison kills 1 player.")
        save.append("witch saved")

    if has("hunter"):
        mech.append("Hunter: if killed by wolf, may shoot 1 player before death.")

    if has("knight"):
        mech.append("Knight: once in own day speech turn may challenge 1 player; if player=wolf, wolf dies, else both die; day ends, no vote.")

    # ----------------------------
    # night order
    # ----------------------------
    night = []

    if has("seer"):
        night.append("Seer")

    if has("werewolf") or has("werewolves"):
        night.append("Werewolves")

    if has("guardian angel"):
        night.append("Guardian Angel")

    if has("witch"):
        night.append("Witch")

    if has("hunter"):
        night.append("Hunter(if triggered)")

    night_order = " -> ".join(night)

    # ----------------------------
    # text
    # ----------------------------
    text = f"""
Setup: {player_number} players. Roles: {roles}. One fixed role each.
Teams: Werewolves vs Village (all others)

- Only werewolves know teammates.
- EVERYONE MAY LIE; EVERYONE CAN LIE.

Win:
- Wolves: all Village dead.
- Village: all Wolves dead.
- All dead = tie.

Loop:
Night: {night_order}.
{"\n".join(mech[:-1]) if has("knight") else "\n".join(mech)}
Night deaths resolve {(f"(no deaths last night may imply {'/'.join(save)})") if save else ""}.
(wolf may self-kill or no_kill BUT EXTREMELY RARE)
Day: announce dead names only -> 2 public discussion rounds -> vote.
Discussion: speech is IN TURN, no speech yet (quiet)=NOT THEIR TURN YET.
Vote: most votes eliminated; tie=NO elimination.
Werewolf may reveal in day: self dies, day ends, no vote.
{mech[-1] if has("knight") else ""}
Dead players cannot speak, act, or be targeted.
"""
    
    return {
        "Werewolves_Table": {
            "description": text.strip(),
            "severity": 100
        }
    }

def initialize_game_state(player_number, flexible_role):
    scene = scene_template()
    world = world_template()
    game_rounds = game_round_template()

    # ---- role config ----
    if player_number == 7:
        roles = f"2 werewolves, 3 villagers, 1 seer, 1 {flexible_role}"
    elif player_number == 10:
        roles = f"3 werewolves, 4 villagers, 1 seer, 1 witch, 1 {flexible_role}"
    else:
        player_number = 14
        roles = "4 werewolves, 5 villagers, 1 seer, 1 witch, 1 hunter, 1 knight, 1 guardian angel"

    # ---- Fill scene ----
    scene["location"] = {
        "key": "table_werewolves",
        "name": "table",
        "description": "A large round table where all players gather for Werewolves Table game."
    }
    scene["environment"] = {
        "table": {
            "description": "All players are seated around a large round table, clearly seeing and hearing each other. The entire game takes place at this table with no movement or spatial separation.",
            "severity": 100
        }
    }
    scene["rules"] = game_rule(player_number, roles)

    # ---- World ----
    world["setting"] = "A fully abstract social deduction game taking place around a single table. No physical movement or environmental complexity exists."
    world["rules"] = game_rule(player_number, roles)

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

# didn't log this one
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
            model=random.choice(MODEL_SMALL),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "generate personality for the character"}
            ]
        )
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        return data.get("personality", {})
    except Exception as e:
        log_error("generate_personality_with_llm", e)

# didn't log this one
def generate_appearance_with_llm(gender, age_apparent):
    prompt = (
        "Generate a brief appearance description for a " + gender + " character that is " + str(age_apparent) + " years old.\n\n"
        "Rules:\n"
        "- Keep it VERY SHORT (1-2 sentences)\n"
        "- Focus on distinctive features that can be easily perceived at the table\n\n"
        "Return ONLY PLAIN TEXT."
    )
    try:
        response = client.chat.completions.create(
            model=random.choice(MODEL_SMALL),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "generate appearance for the character"}
            ]
        )
        content = response.choices[0].message.content
        return content.strip()
    except Exception as e:
        log_error("generate_appearance_with_llm", e)
        return ""

def initialize_characters(CHARACTER_NAMES, player_number=10, flexible_role="hunter", IF_INITIAL_TRAITS=False, IF_INITIAL_MODELS=False):
    chars = {"characters": {}}
    chars_profile = load_json(CHARACTERS_PROFILE_FILE, {"characters": {}})

    # ==================================================
    # PLAYER COUNT MODES
    # ==================================================
    if player_number == 7:
        # 2 wolf / 1 seer / 1 flexible / 3 villager
        roles = [
            "werewolf", "werewolf",
            "seer",
            flexible_role,
            "villager", "villager", "villager"
        ]
    elif player_number == 10:
        # 3 wolf / 1 seer / 1 witch / 1 flexible / 4 villager
        roles = [
            "werewolf", "werewolf", "werewolf",
            "seer",
            "witch",
            flexible_role,
            "villager", "villager", "villager", "villager"
        ]
    else:
        # 14 players
        # 4 wolf / 5 villager / seer witch hunter knight angel
        roles = [
            "werewolf", "werewolf", "werewolf", "werewolf",
            "villager", "villager", "villager", "villager", "villager",
            "seer",
            "witch",
            "hunter",
            "knight",
            "guardian_angel"
        ]
    roles = roles[:player_number]
    random.shuffle(roles)

    # ==================================================
    # MODEL POOL
    # ==================================================
    model_pool = (
        ["llama-3.3-70b-versatile"] * max(1, player_number // 2) +
        ["openai/gpt-oss-120b"] * max(1, player_number // 2 + 1)
    )
    # model_pool = (
    #     ["openai/gpt-oss-120b"] * max(1, player_number)
    # )
    random.shuffle(model_pool)

    # ==================================================
    # INIT EACH CHARACTER
    # ==================================================
    for idx, (name, role) in enumerate(zip(CHARACTER_NAMES, roles)):
        profile = chars_profile["characters"].get(name, {})

        char = character_template()
        char["name"] = name

        # ------------------------------------------------
        # TRAITS
        # ------------------------------------------------
        if IF_INITIAL_TRAITS:
            # fresh random traits
            char["gender"] = random.choice(["male", "female"])
            char["age_apparent"] = random.randint(18, 26)
            char["age_actual"] = char["age_apparent"] + random.randint(0, 3)
            char["species"] = "human"
            # ---- appearance via LLM----
            char["appearance"] = {
                "general": {
                    "description": generate_appearance_with_llm(char["gender"], char["age_apparent"]),
                    "value": random.randint(70, 80)
                }
            }
            # ---- personality via LLM ----
            personality = generate_personality_with_llm()
            if personality:
                char["personality"] = personality
        else:
            # pull traits from profile. fallback: minimal state
            source = profile
            char["gender"] = source.get("gender", "unknown")
            char["age_apparent"] = source.get("age_apparent", 20)
            char["age_actual"] = source.get("age_actual", char["age_apparent"])
            char["species"] = source.get("species", "human")
            char["appearance"] = source.get("appearance", {})
            char["personality"] = source.get("personality", {})

        # ------------------------------------------------
        # MODEL
        # ------------------------------------------------
        if IF_INITIAL_MODELS:
            char["llm_model"] = model_pool[idx % len(model_pool)]
        else:
            source = profile
            char["llm_model"] = source.get("llm_model", model_pool[idx % len(model_pool)])

        # ---- goal ----
        char["goals"] = {"win_the_game": {"description": "win the game for their team", "value": 100}}

        # ---- ongoing process ----
        char["ongoing_processes"] = {"playing_the_game": {"description": "playing the game and aiming to win", "value": 100}}

        # ---- mental state ----
        char["mental_state"] = {"calmness": {"description": "clarity of thought", "value": 70}}

        # ---- location / activity ----
        char["location"] = "table"
        char["activity"] = "sitting at the table"

        # ---- game status ----
        char["game_status"] = {
            "role": role,
            "team": get_team(role),
            "ability": get_ability(role),
            "is_dead": False
        }

        chars["characters"][name] = char

    save_json(CHARACTERS_FILE, chars)

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
        }
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
        mem_snippet = {
            "memory_owner": name,
            "source_type": "heard",
            "phase_step": "game_start",
            "content": {
                "performer": "announcement",
                "announcement": "the game has started."
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        char["memory"]["recent"].setdefault("game_start",[]).append(mem_snippet)

    for name, char in chars.get("characters", {}).items():
        char["knowledge"]["scene"]["characters_present"] = scene["characters_present"]
        for others, char_others in scene["characters_present"].items():
            if others != name:
                char["knowledge"]["characters"][others] = knowledge_character_entry_template()
                char["knowledge"]["characters"][others]["basics"]["gender"] = {"value": chars["characters"][others].get("gender"), "confidence": 100}
                char["knowledge"]["characters"][others]["basics"]["age_apparent"] = {"value": chars["characters"][others].get("age_apparent"), "confidence": 90}
                char["knowledge"]["characters"][others]["basics"]["appearance"] = {"description": chars["characters"][others]["appearance"]["general"]["description"], "confidence": 90}
                char["knowledge"]["characters"][others]["goals"] = {"win_the_game": {"description": "win the game for their team", "value": 100, "confidence": 100}}
                char["knowledge"]["characters"][others]["state"]["location"] = {"value": "table", "confidence": 100}
                char["knowledge"]["characters"][others]["state"]["activity"] = {"description": "sitting at the table playing the game", "confidence": 100}
                char["knowledge"]["characters"][others]["game_status"]["is_dead"] = {"value": False, "confidence": 100}
                if char["game_status"]["team"] == "werewolf":
                    if chars["characters"][others]["game_status"]["team"] == "werewolf":
                        char["knowledge"]["characters"][others]["game_status"]["role"] = {"value": "werewolf", "confidence": 100}
                        char["knowledge"]["characters"][others]["game_status"]["team"] = {"value": "werewolf", "confidence": 100}
                        char["knowledge"]["characters"][others]["game_status"]["ability"] = {"value": "kill_at_night", "confidence": 100}

    save_json(CHARACTERS_FILE, chars)
    save_json(SCENE_STATE_FILE, scene)

# =========================
# LLM VIEW
# =========================
def prune_empty(obj):
    """
    Recursively remove:
    - empty dict {}
    - empty list []
    - None
    - ""
    Keeps 0 / False / valid values.
    """
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            new_v = prune_empty(v)

            if new_v in ({}, [], None, ""):
                continue
            
            cleaned[k] = new_v

        return cleaned

    elif isinstance(obj, list):
        cleaned = []
        for item in obj:
            new_item = prune_empty(item)

            if new_item in ({}, [], None, ""):
                continue

            cleaned.append(new_item)

        return cleaned

    else:
        return obj

def filter_memory_for_llm(memory):
    """
    recent:
        keep direct keys
        move content fields outward
    mid:
        keep as-is
    """

    if not isinstance(memory, dict):
        return {}

    out = {}
    # =================================================
    # RECENT
    # =================================================
    recent = memory.get("recent", {})
    if isinstance(recent, dict):
        out["recent"] = {}
        for phase_key, bucket in recent.items():
            if not isinstance(bucket, list):
                continue

            cleaned_bucket = []
            for rec in bucket:
                if not isinstance(rec, dict):
                    continue

                content = rec.get("content", {})
                if not isinstance(content, dict):
                    continue

                small = {}
                # move content fields directly outward
                for k, v in content.items():
                    if k == "internal_reasoning":
                        continue
                    small[k] = v
                if small:
                    cleaned_bucket.append(small)

            if cleaned_bucket:
                out["recent"][phase_key] = cleaned_bucket

    # =================================================
    # MID
    # keep as-is
    # =================================================
    mid = memory.get("mid", {})
    if isinstance(mid, dict) and mid:
        out["mid"] = mid

    return out

def build_llm_view(chars, actor_name):
    actor = chars["characters"][actor_name]
    game = load_json(GAME_ROUNDS_FILE, game_round_template())

    # -------------------------------------------------
    # SELF APPEARANCE
    # only general.description
    # too noisy, not now.
    # -------------------------------------------------
    # self_appearance = (actor.get("appearance", {}).get("general", {}).get("description", ""))

    # -------------------------------------------------
    # SELF PERSONALITY
    # convert:
    # { empathy:{description..., value:70}, caution:{...} }
    # ->
    # ["empathy (70)", "caution (55)"]
    # too noisy, not now.
    # -------------------------------------------------
    # personality_out = []
    # for trait_name, trait_data in actor.get("personality", {}).items():
    #     if isinstance(trait_data, dict):
    #         val = trait_data.get("value", "")
    #         personality_out.append(f"{trait_name} ({val})")
    #     else:
    #         personality_out.append(str(trait_name))

    # -------------------------------------------------
    # CHARACTERS PRESENT
    # keep only names
    # -------------------------------------------------
    present_raw = actor.get("knowledge", {}).get("scene", {}).get("characters_present", {})
    if isinstance(present_raw, dict):
        present_names = list(present_raw.keys())
    elif isinstance(present_raw, list):
        present_names = present_raw
    else:
        present_names = []

    # -------------------------------------------------
    # BASE VIEW
    # -------------------------------------------------
    view = {
        "name": actor_name,
        "gender": actor.get("gender", "unknown"),
        "age": actor.get("age_actual", 20),

        # "appearance": self_appearance,
        # "personality": personality_out,

        "game_status": actor.get("game_status", {}),

        "knowledge": {
            "game_rules": actor["knowledge"]["scene"]["rules"].get("Werewolves_Table", {}).get("description", ""),
            "characters_present": present_names,
            "characters": {}
        },

        "memory": filter_memory_for_llm(actor.get("memory", {}))
    }

    view["game_status"]["current_round"] = game.get("current_round", 0)

    # -------------------------------------------------
    # OTHER CHARACTERS KNOWLEDGE
    # keep ONLY selected fields:
    # gender / age / appearance / game_status
    # and prune values to "value" when applicable
    # -------------------------------------------------
    for name, target in chars["characters"].items():
        if name == actor_name:
            continue

        source = actor["knowledge"]["characters"].get(name, {})

        basics = source.get("basics", {})
        game_status = source.get("game_status", {})

        # # appearance
        # # not now, too noisy
        # app = basics.get("appearance", "")
        # if isinstance(app, dict) and "description" in app:
        #     app = app["description"]

        # prune game_status fields if nested {value:...}
        gs_out = {}
        for k, v in game_status.items():
            if isinstance(v, dict) and "value" in v:
                gs_out[k] = v["value"]
            else:
                gs_out[k] = v

        view["knowledge"]["characters"][name] = {
            "gender": basics.get("gender", {}).get("value", "unknown"),
            "age": basics.get("age_apparent", {}).get("value", 20),
            # "appearance": app,
            "game_status": gs_out
        }

    return prune_empty(view)

# =========================
# CALL LLM
# =========================
ALL_CHARACTER_NAMES = [
    "AA", "GA", "MA", "PA", "SA", "VA", "YA",
    "CX", "DX", "FX", "LX", "NX", "TX", "WX"
]
ALL_ROLES = ["werewolf", "villager", "seer", 
    "witch", "hunter", "knight", "guardian angel"
]
SOCIAL_VERBS = {"suspect", "accuse", "oppose", "kill",
    "trust", "defend", "ally", "agree", "save",
    "roleclaim (ROLE)", "roledoubt (ROLE)",
    "unsure", "observe",
    "wait"
}
THOUGHT_VERBS = {"belief", "goal", "plan", "risk"}

def system_prompt_rules():
    rules = """
You are simulating a character in a fully abstract structured social deduction game; YOU are the character.
There's NO environmental complexity, NO physical movement, NO sight perception.

Rules:
- Use ONLY information in the input; Do NOT invent or assume facts.
- MAY use memory and knowledge. But DO NOT RECAP unless directly useful.
- DO NOT overthink. Information is limited, uncertainty is natural.

Output:
"""
    return rules.strip()

def system_prompt_speak():
    speak = f"""
{system_prompt_rules()}
- Speech to others.

IMPORTANT:
- Output ONLY important strategic item
- ONE item per line
- Do NOT force; 0-3 items are ENOUGH
- Be SHORT AND COMPRESSED
- 3-10 words per item are ENOUGH

SPEECH ITEM FORMAT:
message|reasons PRESENTED TO OTHERS (can be NONE)

Speech message verbs reference:
{", ".join(SOCIAL_VERBS)}
With target's NAME attached if applicable, eg. "defend AA".

Example:
roleclaim self seer|NONE
defend AA|inspected AA last night, village

-----
OUTPUT FORMAT:

speech:
<<<
lines here OR EMPTY
>>>
"""
    return speak.strip()

def system_prompt_answering():
    vote = f"""
{system_prompt_rules()}
- Select ONE answer from the provided valid options, any other answer will count as pass.

-----
OUTPUT FORMAT:

answer:
<<<
your selected option
>>>
"""
    return vote.strip()

def build_payload_speak(character_information, phase_step, reminder="", extras=None):
    payload = {
        "YOUR(character)_information": character_information,
        "phase_step": phase_step,
        "reminder": reminder
    }
    if extras:
        payload.update(extras)

    return payload

def build_payload_answer(character_information, phase_step, question, valid_options, reminder="", extras=None):
    payload = {
        "YOUR(character)_information": character_information,
        "phase_step": phase_step,
        "reminder": reminder,
        "question": question,
        "valid_options": valid_options
    }
    if extras:
        payload.update(extras)

    return payload

def call_llm(actor_name, model_name, sys_prompt, user_payload, 
    call_type="speech", valid_options=None, default_answer="pass", default_speech=[], max_len=20
):
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
            ]
        )
        raw_content = response.choices[0].message.content

    except Exception as e:
        log_error(f"{actor_name}_{call_type}_llm_call", e)
        raw_content = ""
    
    # prevent spamming the model
    time.sleep(4)

    # =====================================================
    # SPEECH MODE
    # =====================================================
    if call_type == "speech":
        data = parse_llm_output(raw_text=raw_content, mode="speak", default_speech=default_speech)
        
        speech = data.get("speech", default_speech)
        if speech != default_speech:
            internal_reasoning = data.get("internal_reasoning", [])
        else:
            internal_reasoning = []
        
        result = {
            "internal_reasoning": internal_reasoning,
            "speech": speech,
            "raw_content": raw_content
        }

        log_llm_interaction(actor_name, call_type, str(sys_prompt)+"\n"+str(user_payload), raw_content,
            {
                "speech": result["speech"],
                "internal_reasoning": result["internal_reasoning"]
            }
        )

        return result

    # =====================================================
    # ANSWER MODE
    # =====================================================
    else:
        data = parse_llm_output(raw_text=raw_content, mode="answer", 
            valid_options=valid_options, default_answer=default_answer)

        answer = data.get("answer", default_answer)
        if answer != default_answer:
            internal_reasoning = data.get("internal_reasoning", [])
        else:
            internal_reasoning = []
        
        result = {
            "internal_reasoning": internal_reasoning,
            "answer": answer,
            "raw_content": raw_content
        }

        log_llm_interaction(actor_name, call_type, str(sys_prompt)+"\n"+str(user_payload), raw_content,
            {
                "normalized_answer": result["answer"],
                "internal_reasoning": result["internal_reasoning"]
            }
        )

        return result

# =========================
# MEMORY HELPERS
# =========================
def dedupe_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def signal_merge_key(signal):
    """
    hostile AA
    trust AA
    roleclaim AA seer
    """

    s = signal.lower()

    hostile_words = ["suspect", "distrust", "accuse", "oppose", "kill", "eliminate"]
    support_words = ["agree_with", "trust", "defend", "ally", "save", "alliance"]
    neutral_words = ["observe"]

    for n in ALL_CHARACTER_NAMES:
        if n.lower() in s.lower():
            target = n

    if not target:
        return s

    if any(w in s for w in hostile_words):
        return f"hostile:{target}"

    if any(w in s for w in support_words):
        return f"support:{target}"

    if any(w in s for w in neutral_words):
        return f"neutral:{target}"

    return s

def signals_override(signals):
    """
    count the amount of signals that are about the same target in the list.
    keep the one with the most amount, delete the others. if tie, delete all.
    return the final list after override.
    """

def extract_signals(entries, allowed_verbs=None, valid_names=None):
    """
    Extract only the first field
    """

    if not entries:
        return []

    if isinstance(entries, str):
        entries = entries.splitlines()

    allowed_verbs = set(allowed_verbs or [])
    valid_names = set(valid_names or [])

    out = []
    seen = set()
    for raw in entries:
        if not raw:
            continue

        line = str(raw).strip()

        if not line:
            continue

        # normalize spacing around |
        line = re.sub(r'\s*\|\s*', '|', line)
        parts = line.split("|")

        # need at least the first field
        if len(parts) < 1:
            continue

        verb = parts[0].strip()

        # validate verb if provided
        if allowed_verbs and verb not in allowed_verbs:
            continue

        normalized = f"{verb}"

        low = normalized.lower()
        if low in seen:
            continue

        seen.add(low)
        out.append(normalized)

    return out

# --------------------------------------------------
# SELF
# --------------------------------------------------
def route_self_bucket(bucket, slot, content):
    """
    self bucket:
    {
        "day_1": [
            {"speech":[...], "internal_reasoning":[...]},
            {"action":"voted...", "internal_reasoning":[...]}
        ]
    }
    """

    speech = content.get("speech", [])
    internal_reasoning = content.get("internal_reasoning", [])
    action = content.get("action", "")
    performer = content.get("performer", "unknown")

    bucket.setdefault(slot, [])
    arr = bucket[slot]

    # -----------------------------
    # speech event
    # -----------------------------
    if speech:
        signals = extract_signals(speech)
        if signals:
            signals = dedupe_keep_order(signals)
            arr.append({"speech": signals, "internal_reasoning": internal_reasoning})

    # -----------------------------
    # action event
    # always append. for now.
    # -----------------------------
    if action:
        arr.append({"action": action, "internal_reasoning": internal_reasoning})

# --------------------------------------------------
# OTHERS
# --------------------------------------------------
def route_other_bucket(bucket, slot, content):
    """
    bucket = {slot: [events]}
    """

    speech = content.get("speech", [])
    action = content.get("action", "")
    performer = content.get("performer", "unknown")

    signals = extract_signals(speech) if speech else []

    # discard empty speech entirely
    has_anything = bool(signals or action)
    if not has_anything:
        return

    bucket.setdefault(slot, [])
    timeline = bucket[slot]

    # -----------------------------
    # speech
    # merge only if latest item is speech
    # -----------------------------
    if signals:
        signals = dedupe_keep_order(signals)
        if (timeline and isinstance(timeline[-1], dict) and "speech" in timeline[-1]):
            old = timeline[-1].get("speech", [])
            timeline[-1]["speech"] = dedupe_keep_order(old + signals)
        else:
            timeline.append({"speech": signals})

    # -----------------------------
    # action
    # always append as next event
    # -----------------------------
    if action:
        timeline.append({"action": action})

def route_recent_mem_to_mid(char, recent_key, mem):
    """
    MID STRUCTURE:
    {
        "self": {},
        "announcement": {},
        "AA": {
            "day_1": [
                {"speech":[...]}, 
                {"action":"voted..."}
            ]
        },
        ...
    }
    """

    memory = char.setdefault("memory", {})
    mid = memory.setdefault("mid", {})

    # -------------------------
    # extract slot name
    # round_3_day_discuss_2 -> day_3
    # round_3_night_wolfchat_round_1 -> night_3
    # -------------------------
    s = str(recent_key).lower().strip()
    phase = "night" if "night" in s else "day"

    m = re.search(r'^round_(\d+)', s)
    round_num = int(m.group(1)) if m else 0

    slot = f"{phase}_{round_num}"

    # -------------------------
    content = mem.get("content", {})
    performer = content.get("performer", "unknown")
    source_type = mem.get("source_type", "")

    # -------------------------
    # announcement
    # -------------------------
    if performer == "announcement":
        mid.setdefault("announcement", {})
        result = content.get("result", "")
        if result:
            mid["announcement"].setdefault(slot, []).append(result)
        return

    # -------------------------
    # self
    # -------------------------
    if source_type == "self":
        mid.setdefault("self", {})
        route_self_bucket(mid["self"], slot, content)
        return

    # -------------------------
    # others
    # -------------------------
    mid.setdefault(performer, {})
    route_other_bucket(mid[performer], slot, content)

# --------------------------------------------------
# ENTRY POINT
# call this after adding ONE new recent memory
# --------------------------------------------------
def trim_recent_memory(char, keep_latest=4):
    """
    Keep newest recent raw memories.
    Overflow oldest -> route into MID.
    """

    recent = char.get("memory", {}).get("recent", {})
    if not isinstance(recent, dict):
        return False

    timeline = []
    for phase_key, bucket in recent.items():
        for idx, mem in enumerate(bucket):
            timeline.append((phase_key, idx, mem))

    if len(timeline) <= keep_latest:
        return False

    overflow = len(timeline) - keep_latest
    moved = timeline[:overflow]

    # route oldest overflow first
    for bucket_key, idx, mem in moved:
        route_recent_mem_to_mid(char, bucket_key, mem)
        recent[bucket_key][idx] = None

    # cleanup
    for k in list(recent.keys()):
        arr = [x for x in recent[k] if x is not None]
        if arr:
            recent[k] = arr
        else:
            del recent[k]

    return True

# =========================
# DECISIONS
# =========================
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

def ask_llm_for_target(chars, actor_name, action_type, action_target):
    game_round = load_json(GAME_ROUNDS_FILE, {})
    view = build_llm_view(chars, actor_name)

    # ---- question ----
    if action_type == "seer":
        question = "You are the Seer. Which player do you want to inspect tonight?"
        mem_action = "inspected"

    elif action_type == "guardian_angel":
        question = "You are the Guardian Angel. Which player do you want to protect tonight? (you cannot protect the same player as last night)"
        mem_action = "protected"

    elif action_type == "witch_save":
        question = f"You are the Witch. The player '{action_target}' is going to die tonight. Do you want to use your save potion? (you only have ONE save potion for the entire game)"
        mem_action = f"if SAVED {action_target}:"

    elif action_type == "witch_poison":
        question = "You are the Witch. Which player do you want to poison tonight, or choose no one?"
        mem_action = "poisoned:"

    elif action_type == "hunter":
        question = "You are the Hunter. You are going to die tonight. Which player do you want to shoot? or no one?"
        mem_action = "shot"

    else:
        return None

    # ---- set valid selection range ----
    if action_type in ["seer", "witch_poison", "hunter"]:
        valid_range_of_selection = get_valid_targets(chars, exclude=[]) + ["no_action"]
    elif action_type == "guardian_angel":
        valid_range_of_selection = get_valid_targets(chars, exclude=[view["game_status"]["ability"].get("last_protected")])
    else:
        valid_range_of_selection = ["yes", "no"]
    
    # ---- call llm ----
    SYSTEM_PROMPT = system_prompt_answering()
    payload = build_payload_answer(
        view,
        f"night_action_{action_type}",
        question=question,
        valid_options=valid_range_of_selection,
        reminder="help your TEAM WIN the game"
    )
    model = chars["characters"][actor_name]["llm_model"]

    result = call_llm(actor_name, model, SYSTEM_PROMPT, payload, "answer", valid_range_of_selection)
    answer = result.get("answer", "pass")
    internal_reasoning = result.get("internal_reasoning", [])

    res = ""
    if action_type == "seer" and answer in valid_range_of_selection:
        team = chars["characters"][answer]["game_status"]["team"]
        res = f"; result: {team}"

    # ---- use output ----
    mem_snippet = {
        "memory_owner": actor_name,
        "source_type": "self",
        "phase_step": f"night_action_{action_type}",
        "content": {
            "performer": actor_name,
            "action": f"{(mem_action + ' ' + answer + res) if answer != 'no_action' and answer != 'pass' else f'{mem_action} None'}",
            "internal_reasoning": internal_reasoning
        },
        "metadata":{
            "impact": 100,
            "confidence": 100
        }
    }
    current_round = game_round.get("current_round", 0)
    chars["characters"][actor_name]["memory"]["recent"].setdefault(f"round_{current_round}_night_{action_type}",[]).append(mem_snippet)

    trim_recent_memory(chars["characters"][actor_name])

    return answer

# didn't load this into memory
def ask_wolf_ready_to_vote(view, mod):
    SYSTEM_PROMPT_CONSENSUS = system_prompt_answering()
    valid_options = ["yes", "no"]
    payload = build_payload_answer(
        view,
        "night_wolfchat_cut_short",
        question="do you want to end the discussion early and proceed to vote directly?",
        valid_options=valid_options,
        reminder="Choose 'yes' if you think a consensus is reached and there's no need to discuss further"
    )

    result = call_llm("", mod, SYSTEM_PROMPT_CONSENSUS, payload, "answer", valid_options)

    return result["answer"] == "yes"

def ask_llm_for_target_wolves(chars, wolves):
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
    SYSTEM_PROMPT_DISCUSSION = system_prompt_speak()

    # =====================================
    # 3 ROUNDS PRIVATE DISCUSSION
    # =====================================
    alive = [
        wolf for wolf in wolves
        if not chars["characters"][wolf]["game_status"]["is_dead"]
    ]
    for discuss_round in range(1, 4):
        if len(alive) <= 1:
            break
        for speaker in speak_order:
            # skip dead during phase (future-proof)
            if chars["characters"][speaker]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(chars, speaker)
            payload = build_payload_speak(
                view,
                f"night_wolfchat_round_{discuss_round}",
                reminder="Coordinate with werewolves to determine the target to kill tonight. Help your TEAM WIN the game."
            )
            model=chars["characters"][speaker]["llm_model"]

            result = call_llm(speaker, model, SYSTEM_PROMPT_DISCUSSION, payload, "speech")
            speech = result.get("speech", "...")
            internal_reasoning = result.get("internal_reasoning", "")

            # ---------------------------------
            # speaker remembers own action
            # ---------------------------------
            mem_snippet = {
                "memory_owner": speaker,
                "source_type": "self",
                "phase_step": f"night_wolfchat_round_{discuss_round}",
                "content": {
                    "performer": speaker,
                    "speech": speech,
                    "internal_reasoning": internal_reasoning
                },
                "metadata":{
                    "impact": 100,
                    "confidence": 100
                }
            }
            chars["characters"][speaker]["memory"]["recent"].setdefault(
                f"round_{current_round}_night_wolfchat_round_{discuss_round}",[]).append(mem_snippet)
            
            trim_recent_memory(chars["characters"][speaker])

            # ---------------------------------
            # other wolves hear + remember
            # ---------------------------------
            for listener in wolves:
                if listener == speaker:
                    continue
                if chars["characters"][listener]["game_status"]["is_dead"]:
                    continue

                mem_snippet = {
                    "memory_owner": listener,
                    "source_type": "heard",
                    "phase_step": f"night_wolfchat_round_{discuss_round}",
                    "content": {
                        "performer": speaker,
                        "speech": speech,
                    },
                    "metadata":{
                        "impact": 80,
                        "confidence": 100
                    }
                }
                chars["characters"][listener]["memory"]["recent"].setdefault(
                    f"round_{current_round}_night_wolfchat_round_{discuss_round}",[]).append(mem_snippet)
                
                trim_recent_memory(chars["characters"][listener])
        
        votes = []
        alive_wolves = [
            voter for voter in speak_order
            if not chars["characters"][voter]["game_status"]["is_dead"]
        ]
        for voter in alive_wolves:
            view = build_llm_view(chars, voter)
            decision = ask_wolf_ready_to_vote(view, chars["characters"][voter]["llm_model"])
            votes.append(decision)
        # ---------------------------------
        # Majority agreement ends discussion
        # ---------------------------------
        yes_count = sum(1 for v in votes if v)
        if yes_count > len(alive_wolves) / 2:
            break

    # =====================================
    # VOTING PHASE
    # =====================================
    SYSTEM_PROMPT_VOTE = system_prompt_answering()
    votes = {}
    for wolf in wolves:
        if chars["characters"][wolf]["game_status"]["is_dead"]:
            continue

        view = build_llm_view(chars, wolf)
        valid_targets = get_valid_targets(chars, exclude=[])
        valid_vote_options = valid_targets + ["no_kill"]

        payload = build_payload_answer(
            view,
            "night_wolfvote",
            question="Who will be the target to kill tonight?",
            valid_options=valid_vote_options,
            reminder="Vote effectively and help Team Werewolf WIN the game"
        )
        model=chars["characters"][wolf]["llm_model"]

        result = call_llm(wolf, model, SYSTEM_PROMPT_VOTE, payload, "answer", valid_vote_options)
        answer = result.get("answer", "pass")
        internal_reasoning = result.get("internal_reasoning", "")

        if answer != "pass":
            votes[answer] = votes.get(answer, 0) + 1

        # ---------------------------------
        # wolf (voter) remembers
        # ---------------------------------
        mem_snippet = {
            "memory_owner": wolf,
            "source_type": "self",
            "phase_step": "night_wolfvote",
            "content": {
                "performer": wolf,
                "action": f"voted for {answer} as the target to kill tonight" if answer != "pass" else "abstained",
                "internal_reasoning": internal_reasoning
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][wolf]["memory"]["recent"].setdefault(
            f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)

        trim_recent_memory(chars["characters"][wolf])

        # ---------------------------------
        # other wolves get the result of this vote too
        # ---------------------------------
        for observer in wolves:
            if observer == wolf:
                continue
            if chars["characters"][observer]["game_status"]["is_dead"]:
                continue
            
            mem_snippet = {
                "memory_owner": observer,
                "source_type": "observed",
                "phase_step": "night_wolfvote",
                "content": {
                    "performer": wolf,
                    "action": f"voted for {answer} as the target to kill tonight" if answer != "pass" else "abstained",
                },
                "metadata":{
                    "impact": 90,
                    "confidence": 100
                }
            }
            chars["characters"][observer]["memory"]["recent"].setdefault(
                f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)
            
            trim_recent_memory(chars["characters"][observer])

    # =====================================
    # RESOLVE VOTE
    # =====================================
    if not votes:
        result = None
    else:
        highest = max(votes.values())
        top = [name for name, count in votes.items() if count == highest]

        # tie = no kill
        if len(top) != 1:
            result = None
        else:
            result = top[0]

        if result == "no_kill":
            result = None
    
    # ---------------------------------
    # SHARE VOTING RESULTS TO ALL WOLVES
    # ---------------------------------
    for wolf in wolves:
        if chars["characters"][wolf]["game_status"]["is_dead"]:
            continue

        mem_snippet = {
            "memory_owner": wolf,
            "source_type": "heard",
            "phase_step": "night_wolfvote",
            "content": {
                "performer": "announcement",
                "announcement": f"votes: {votes}",
                "result": f"wolfkill_target: {result if result else 'no_kill'}"
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][wolf]["memory"]["recent"].setdefault(
            f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)

        trim_recent_memory(chars["characters"][wolf])

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
        target = ask_llm_for_target(chars, seer, "seer", None)

        if is_valid_target(target, chars) and target != seer:
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
        target = ask_llm_for_target_wolves(chars, wolves)

        if is_valid_target(target, chars):
            night_state["werewolf_target"] = target

    # =========================
    # 3. GUARDIAN ANGEL
    # =========================
    guardian = get_alive_role(chars, "guardian_angel")
    if guardian:
        char = chars["characters"][guardian]
        last = char["game_status"]["ability"].get("last_protected")

        target = ask_llm_for_target(chars, guardian, "guardian_angel", None)

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
            use_save = ask_llm_for_target(chars, witch, "witch_save", wolf_target)
            if use_save == "yes":
                night_state["werewolf_target"] = None
                ability["save_potion"] -= 1

        # ---- POISON ----
        if ability.get("poison_potion", 0) > 0:
            poison_target = ask_llm_for_target(chars, witch, "witch_poison", None)

            if is_valid_target(poison_target, chars):
                night_state["witch_poison_target"] = poison_target
                ability["poison_potion"] -= 1

    # =========================
    # 5. HUNTER
    # =========================
    wolf_target = night_state["werewolf_target"]
    if wolf_target and chars["characters"][wolf_target]["game_status"]["role"] == "hunter":
        shot = ask_llm_for_target(chars, wolf_target, "hunter", None)

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
        announcement_text = f"Morning Announcement: The following players died last night: {', '.join(deaths)}."
    else:
        announcement_text = "Morning Announcement: No one died last night."
    
    # LOGGING
    public_event(announcement_text + "\n")

    for name, char in chars["characters"].items():
        # dead players don't receive updates
        if char["game_status"]["is_dead"]:
            continue
        # ---------------------------------
        # MEMORY UPDATE
        # ---------------------------------
        mem_snippet = {
            "memory_owner": name,
            "source_type": "heard",
            "phase_step": "morning_announce_last_night_deaths",
            "content": {
                "performer": "announcement",
                "result": f"last_night_deaths: {', '.join(deaths)}" if deaths else "no_deaths_last_night"
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        char["memory"]["recent"].setdefault(
            f"round_{current_round}_morning_announcement",[]).append(mem_snippet)
        
        trim_recent_memory(chars["characters"][name])

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

# =========================
# GAME PHASES - DAY
# =========================
def knight_challenge(chars, speaker, view, valid_targets, current_round):
    SYSTEM_PROMPT_CHALLENGE = system_prompt_answering()

    ability = chars["characters"][speaker]["game_status"]["ability"]

    if ability.get("challenge_chance", 0) <= 0:
        return False
    
    payload = build_payload_answer(
        view,
        "day_knight_interrupt",
        question="Use Knight challenge? If yes, answer the target's name. If no, answer 'no'.",
        valid_options=valid_targets + ["no"],
        reminder="If your target isn't a werewolf, you BOTH DIE. Use ONLY if it's worth the risk and HELP YOUR TEAM WIN THE GAME."
    )
    model=chars["characters"][speaker]["llm_model"]

    result = call_llm(speaker, model, SYSTEM_PROMPT_CHALLENGE, payload, "answer", valid_targets + ["no"])
    answer = result.get("answer", "pass")
    internal_reasoning = result.get("internal_reasoning", "")

    # =====================================
    # NO CHALLENGE
    # =====================================
    if answer == "no" or answer not in valid_targets:
        mem_key = f"round_{current_round}_day_knight_no_challenge"
        chars["characters"][speaker]["memory"]["recent"].setdefault(mem_key, []).append({
            "memory_owner": speaker,
            "source_type": "self",
            "phase_step": "day_knight_decision",
            "content": {
                "performer": speaker,
                "action": "did not use knight challenge",
                "internal_reasoning": internal_reasoning
            },
            "metadata": {
                "impact": 60,
                "confidence": 100
            }
        })

        trim_recent_memory(chars["characters"][speaker])
        
        return False

    # =====================================
    # CHALLENGE USED
    # =====================================
    ability["challenge_chance"] = 0
    chars["characters"][answer]["game_status"]["is_dead"] = True

    target_role = chars["characters"][answer]["game_status"]["role"]
    result = f"{answer}, the werewolf, died; challenge succeeded"
    if target_role != "werewolf":
        chars["characters"][speaker]["game_status"]["is_dead"] = True
        result = "both_dead"

    # =====================================
    # PUBLIC MEMORY TO ALL ALIVE
    # =====================================
    mem_key = f"round_{current_round}_day_knight_challenge"
    for name, c in chars["characters"].items():
        if c["game_status"]["is_dead"]:
            continue
        if name == speaker:
            c["memory"]["recent"].setdefault(mem_key, []).append({
                "memory_owner": name,
                "source_type": "self",
                "phase_step": "day_knight_challenge",
                "content": {
                    "performer": speaker,
                    "action": f"{speaker}, the knight, challenged {answer}; result: {result}",
                    "internal_reasoning": internal_reasoning
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            })
        else:
            c["memory"]["recent"].setdefault(mem_key, []).append({
                "memory_owner": name,
                "source_type": "observed",
                "phase_step": "day_knight_challenge",
                "content": {
                    "performer": speaker,
                    "action": f"{speaker}, the knight, challenged {answer}; result: {result if result != "both_dead" else f'{answer} is Team Village; both dead'}",
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            })
            c["knowledge"]["characters"][speaker]["game_status"]["role"] = {"value": "knight", "confidence": 100}
            c["knowledge"]["characters"][speaker]["game_status"]["team"] = {"value": "village", "confidence": 100}
            c["knowledge"]["characters"][speaker]["game_status"]["ability"] = {"value": "no_challenge_chance", "confidence": 100}
        
        trim_recent_memory(chars["characters"][name])

        c["knowledge"]["characters"][answer]["game_status"]["is_dead"] = {"value": True, "confidence": 100}
        if result == "both_dead":
            c["knowledge"]["characters"][speaker]["game_status"]["is_dead"] = {"value": True, "confidence": 100}
            c["knowledge"]["characters"][answer]["game_status"]["team"] = {"value": "village", "confidence": 100}
        else:
            c["knowledge"]["characters"][answer]["game_status"]["role"] = {"value": "werewolf", "confidence": 100}
            c["knowledge"]["characters"][answer]["game_status"]["team"] = {"value": "werewolf", "confidence": 100}
            c["knowledge"]["characters"][answer]["game_status"]["ability"] = {"value": "kill_at_night", "confidence": 100}

        c["memory"]["recent"].setdefault(mem_key, []).append({
            "memory_owner": name,
            "source_type": "heard",
            "phase_step": "day_knight_challenge",
            "content": {
                "performer": "announcement",
                "result": f"knight_challenge_caused_death(s): {answer} {', '+speaker if result == 'both_dead' else ''}"
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        })
        trim_recent_memory(chars["characters"][name])
    
    public_event(f"{speaker} challenged {answer}. Result: {result.replace('_', ' ')}.\n")

    return True

def wolf_reveal(chars, speaker, view, current_round):
    SYSTEM_PROMPT_REVEAL = system_prompt_answering()

    payload = build_payload_answer(
        view,
        "day_werewolf_reveal",
        question="Reveal yourself publicly?",
        valid_options=["yes", "no"],
        reminder="Your reveal will kill you, end the discussion and skip the vote. Reveal ONLY if you decide it OBVIOUSLY helps WEREWOLVES WIN DESPITE EXPOSING AND LOSING ONE WOLF (YOU) IMMEDIATELY."
    )
    model=chars["characters"][speaker]["llm_model"]

    result = call_llm(speaker, model, SYSTEM_PROMPT_REVEAL, payload, "answer", ["yes", "no"])
    answer = result.get("answer", "pass")
    internal_reasoning = result.get("internal_reasoning", "")

    # =====================================
    # YES = reveal and die
    # =====================================
    if answer == "yes":
        chars["characters"][speaker]["game_status"]["is_dead"] = True

        # knowledge & memory update
        for name, c in chars["characters"].items():
            if c["game_status"]["is_dead"]:
                continue

            c["knowledge"]["characters"][speaker]["game_status"]["is_dead"] = {"value": True, "confidence": 100}
            c["knowledge"]["characters"][speaker]["game_status"]["role"] = {"value": "werewolf", "confidence": 100}
            c["knowledge"]["characters"][speaker]["game_status"]["team"] = {"value": "werewolf", "confidence": 100}
            c["knowledge"]["characters"][speaker]["game_status"]["ability"] = {"value": "kill_at_night", "confidence": 100}
            
            mem = {
                "memory_owner": name,
                "source_type": "observed",
                "phase_step": "day_wolf_reveal",
                "content": {
                    "performer": speaker,
                    "action": "revealed as werewolf and died"
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            }
            c["memory"]["recent"].setdefault(f"round_{current_round}_day_wolf_reveal", []).append(mem)

            trim_recent_memory(chars["characters"][name])

            c["memory"]["recent"].setdefault(f"round_{current_round}_day_wolf_reveal", []).append({
                "memory_owner": name,
                "source_type": "heard",
                "phase_step": "day_wolf_reveal",
                "content": {
                    "performer": "announcement",
                    "result": f"werewolf_reveal_caused_death: {speaker}"
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            })
            trim_recent_memory(chars["characters"][name])
        
        public_event(f"{speaker} revealed themselves as a werewolf and died!\n")

        return True   # interrupt triggered

    # =====================================
    # NO = private self memory only (not yet. too noisy.)
    # =====================================
    else:
        # mem = {
        #     "memory_owner": speaker,
        #     "source_type": "self",
        #     "phase_step": "day_wolf_reveal_decision",
        #     "content": {
        #         "performer": speaker,
        #         "action": "did not reveal as werewolf",
        #     },
        #     "metadata": {
        #         "impact": 60,
        #         "confidence": 100
        #     }
        # }
        # chars["characters"][speaker]["memory"]["recent"].setdefault(f"round_{current_round}_day_wolf_reveal_decision", []).append(mem)
        
        # trim_recent_memory(chars["characters"][speaker])

        # save_json(CHARACTERS_FILE, chars)
        return False

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
    # RANDOM SPEAK/VOTE ORDER (fixed for day)
    # =====================================
    speak_order = alive_players[:]
    random.shuffle(speak_order)

    # =====================================
    # DISCUSSION
    # =====================================
    SYSTEM_PROMPT_SPEECH = system_prompt_speak()
    for discuss_round in [1, 2]:
        for speaker in speak_order:
            # skip dead mid-phase
            if chars["characters"][speaker]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(chars, speaker)
            role = chars["characters"][speaker]["game_status"]["role"]
            valid_targets = get_valid_targets(chars, exclude=speaker)

            # KNIGHT INTERRUPT
            if role == "knight":
                interrupt_triggered = knight_challenge(chars, speaker, view, valid_targets, current_round)
                if interrupt_triggered:
                    return

            # WEREWOLF REVEAL
            if role == "werewolf":
                interrupt_triggered = wolf_reveal(chars, speaker, view, current_round)
                if interrupt_triggered:
                    return

            # DISCUSSION
            view = build_llm_view(chars, speaker)
            if role == "werewolf":
                payload = build_payload_speak(
                    view,
                    f"day_public_discussion_round_{discuss_round}",
                    reminder="You're discussing who to eliminate today. Your team is WEREWOLF. Your goal is to help your team WIN. "+
                        "You'll want to use STRATEGIES to hide your wolf role, manipulate the village and convince the majoriy to vote with you. "+
                        "BE CAUTIOUS and SUBTLE. DO NOT act like you know any of the night actions or teammates (a village role should NOT know these)."
                )
            else:
                payload = build_payload_speak(
                    view,
                    f"day_public_discussion_round_{discuss_round}",
                    reminder="You're discussing who to eliminate today. Your team is VILLAGE. Your goal is to help your team WIN. "+
                        "You'll want to use STRATEGIES to spot the suspects and convince the majoriy to vote with you "+
                        "BE CAUTIOUS. EVERYONE could be a wolf. DO NOT TRUST EASILY or ACCUSE HASTILY."
                )
            model=chars["characters"][speaker]["llm_model"]

            result = call_llm(speaker, model, SYSTEM_PROMPT_SPEECH, payload, "speech")
            speech = result.get("speech", "...")
            internal_reasoning = result.get("internal_reasoning", "")

            # ---------------------------------
            # SELF MEMORY (speaker spoke)
            # ---------------------------------
            mem_snippet = {
                "memory_owner": speaker,
                "source_type": "self",
                "phase_step": f"day_discuss_round_{discuss_round}",
                "content": {
                    "performer": speaker,
                    "speech": speech,
                    "internal_reasoning": internal_reasoning
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            }
            chars["characters"][speaker]["memory"]["recent"].setdefault(
                f"round_{current_round}_day_discuss_round_{discuss_round}", []).append(mem_snippet)

            trim_recent_memory(chars["characters"][speaker])

            # ---------------------------------
            # OTHERS HEAR SPEECH
            # ---------------------------------

            # DISPLAYING
            public_event(f"{speaker}: {speech}\n")

            for listener in speak_order:
                if listener == speaker:
                    continue
                if chars["characters"][listener]["game_status"]["is_dead"]:
                    continue

                mem_snippet = {
                    "memory_owner": listener,
                    "source_type": "heard",
                    "phase_step": f"day_discuss_round_{discuss_round}",
                    "content": {
                        "performer": speaker,
                        "speech": speech
                    },
                    "metadata": {
                        "impact": 80,
                        "confidence": 100
                    }
                }
                chars["characters"][listener]["memory"]["recent"].setdefault(
                    f"round_{current_round}_day_discuss_round_{discuss_round}", []).append(mem_snippet)

                trim_recent_memory(chars["characters"][listener])

    # =====================================
    # VOTING PHASE
    # =====================================
    SYSTEM_PROMPT_VOTE = system_prompt_answering()
    votes = {}
    for voter in speak_order:
        if chars["characters"][voter]["game_status"]["is_dead"]:
            continue

        view = build_llm_view(chars, voter)
        valid_targets = get_valid_targets(chars, exclude=[])
        valid_options = valid_targets + ["abstain"]
        
        if chars["characters"][voter]["game_status"]["role"] == "werewolf":
            payload = build_payload_answer(
                view,
                "day_public_vote",
                question="Who do you vote to eliminate today?",
                valid_options=valid_options,
                reminder="Your team is WEREWOLF. Help your TEAM WIN the game. Evaluate risk and consider carefully. You can abstain or try to force a tie if it's strategically better."
            )
        else:
            payload = build_payload_answer(
                view,
                "day_public_vote",
                question="Who do you vote to eliminate today?",
                valid_options=valid_options,
                reminder="Your team is VILLAGE. Help your TEAM WIN the game. Evaluate risk and consider carefully. You can abstain or try to force a tie if it's strategically better."
            )
        model=chars["characters"][voter]["llm_model"]

        result = call_llm(voter, model, SYSTEM_PROMPT_VOTE, payload, "answer", valid_options)
        vote = result.get("answer", "pass")
        internal_reasoning = result.get("internal_reasoning", "")
        
        # ---------------------------------
        # SELF MEMORY (vote cast)
        # ---------------------------------
        mem_snippet = {
            "memory_owner": voter,
            "source_type": "self",
            "phase_step": "day_vote",
            "content": {
                "performer": voter,
                "action": f"voted to eliminate {vote}" if vote != "abstain" and vote != "pass" else "abstained",
                "internal_reasoning": internal_reasoning
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][voter]["memory"]["recent"].setdefault(
            f"round_{current_round}_day_vote", []).append(mem_snippet)

        trim_recent_memory(chars["characters"][voter])

        # ---------------------------------
        # OTHERS OBSERVE VOTE
        # ---------------------------------

        # DISPLAYING
        public_event(f"{voter} voted to eliminate {vote}\n" if vote != "abstain" and vote != "pass" else f"{voter} abstained from voting\n")

        for observer in speak_order:
            if observer == voter:
                continue
            if chars["characters"][observer]["game_status"]["is_dead"]:
                continue

            mem_snippet = {
                "memory_owner": observer,
                "source_type": "observed",
                "phase_step": "day_vote",
                "content": {
                    "performer": voter,
                    "action": f"voted to eliminate {vote}" if vote != "abstain" and vote != "pass" else "abstained",
                },
                "metadata": {
                    "impact": 90,
                    "confidence": 100
                }
            }
            chars["characters"][observer]["memory"]["recent"].setdefault(
                f"round_{current_round}_day_vote", []).append(mem_snippet)

            trim_recent_memory(chars["characters"][observer])

        # COUNT THE VOTE:
        if vote not in valid_options:
            vote = "abstain"
        if vote != "abstain":
            votes[vote] = votes.get(vote, 0) + 1

    # =====================================
    # RESOLVE VOTE
    # =====================================
    if votes:
        highest = max(votes.values())
        top = [k for k, v in votes.items() if v == highest]
        if len(top) == 1:
            eliminated = top[0]
            chars["characters"][eliminated]["game_status"]["is_dead"] = True
        else:
            eliminated = None
    else:
        eliminated = None

    # ---------------------------------
    # PUBLIC VOTE RESULT
    # ---------------------------------
    for name, char in chars["characters"].items():
        if char["game_status"]["is_dead"]:
            continue

        mem_snippet = {
            "memory_owner": name,
            "source_type": "heard",
            "phase_step": "day_vote",
            "content": {
                "performer": "announcement",
                "announcement": f"votes: {votes}",
                "result": f"death_by_elimination: {eliminated}" if eliminated else "No elimination today"
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        }
        char["memory"]["recent"].setdefault(
            f"round_{current_round}_day_vote", []).append(mem_snippet)

        trim_recent_memory(chars["characters"][name])

        if eliminated:
            char["knowledge"]["characters"][eliminated]["game_status"]["is_dead"] = {
                "value": True, "confidence": 100}

    # LOGGING
    public_event(f"\nLynch Decision\n{votes}\n{eliminated}\n")

    save_json(CHARACTERS_FILE, chars)

def check_win_conditions():
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

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

def clear_logs():
    for file in [PUBLIC_LOG_FILE, DEBUG_LOG_FILE, LLM_LOG_FILE, LLM_FILTER_FILE]:
        save_text(file, "")

# =========================
# MAIN LOOP
# =========================
def main():
    init_files()

    global ALL_CHARACTER_NAMES
    global ALL_ROLES

    while True:
        raw = input("Do you want to clear logs? (yes / no): ").strip().lower()
        if raw == "yes":
            clear_logs()
            break
        elif raw == "no":
            break
        print("Invalid choice.")

    POWER_ROLES = ["witch", "hunter", "knight", "guardian_angel"]

    chars_profile = load_json(CHARACTERS_PROFILE_FILE, {"characters": {}})
    has_profile = bool(chars_profile.get("characters"))

    # =====================================
    # PLAYER NUMBER
    # =====================================
    while True:
        raw = input("Choose player number (7 / 10 / 14): ").strip()
        if raw in ["7", "10", "14"]:
            player_number = int(raw)
            break
        print("Invalid choice.")

    CHARACTER_NAMES = ALL_CHARACTER_NAMES[:player_number]
    ROLES = []

    # =====================================
    # FLEXIBLE ROLE
    # =====================================
    flexible_role = None
    if player_number == 7:
        ROLES = ["werewolf"] * 2 + ["seer"] + ["villager"] * 3
        valid_flex = POWER_ROLES[:]   # seer already fixed
    elif player_number == 10:
        ROLES = ["werewolf"] * 3 + ["seer"] + ["witch"] + ["villager"] * 4
        valid_flex = ["hunter", "knight", "guardian_angel"]  # seer + witch fixed
    else:
        ROLES = ["werewolf"] * 4 + ["seer"] + ["witch"] + ["hunter"] + ["knight"] + ["guardian_angel"] + ["villager"] * 5
        valid_flex = []

    if valid_flex:
        while True:
            print(f"Choose flexible role: {', '.join(valid_flex)}")
            raw = input("Flexible role: ").strip().lower()
            if raw in valid_flex:
                flexible_role = raw
                break
            print("Invalid choice.")
        
        ROLES.append(flexible_role)
    
    initialize_game_state(player_number, flexible_role)

    # =====================================
    # SHOW SETUP
    # =====================================
    if player_number == 7:
        setup_roles = [
            "2 werewolves",
            "1 seer",
            f"1 {flexible_role}",
            "3 villagers"
        ]
    elif player_number == 10:
        setup_roles = [
            "3 werewolves",
            "1 seer",
            "1 witch",
            f"1 {flexible_role}",
            "4 villagers"
        ]
    else:
        setup_roles = [
            "4 werewolves",
            "5 villagers",
            "1 seer",
            "1 witch",
            "1 hunter",
            "1 knight",
            "1 guardian_angel"
        ]

    print("\n========== GAME SETUP ==========")
    print(f"Players ({player_number}): {', '.join(CHARACTER_NAMES)}")
    print("Role setup:")
    for i, role_text in enumerate(setup_roles, start=1):
        print(f"{i}. {role_text}")
    print("================================\n")

    # =====================================
    # TRAITS OPTION
    # =====================================
    if has_profile:
        while True:
            raw = input("Use randomized traits instead of saved profiles? (yes / no): ").strip().lower()
            if raw == "yes":
                use_random_traits = True
                break
            elif raw == "no":
                use_random_traits = False
                break
            print("Invalid choice.")
    else:
        print("No saved profiles found. Using randomized traits.")
        use_random_traits = True

    # =====================================
    # MODEL OPTION
    # =====================================
    while True:
        raw = input("Reassign LLM models to characters? (yes / no): ").strip().lower()
        if raw == "yes":
            use_random_models = True
            break
        elif raw == "no":
            use_random_models = False
            break
        print("Invalid choice.")

    # =====================================
    # INITIALIZE
    # =====================================
    initialize_characters(CHARACTER_NAMES=CHARACTER_NAMES, player_number=player_number, flexible_role=flexible_role, 
                        IF_INITIAL_TRAITS=use_random_traits, IF_INITIAL_MODELS=use_random_models)
    initialize_characters_scene_world()
    public_event("\n------INITIALIZATION FINISHED------\n")

    ALL_CHARACTER_NAMES = CHARACTER_NAMES[:]
    ALL_ROLES = ROLES[:]

    # =====================================
    # START / QUIT
    # =====================================
    while True:
        cmd = input("Enter 'start' to begin, or 'quit': ").strip().lower()
        if cmd == "quit":
            return
        if cmd == "start":
            break
        print("Invalid choice.")

    # =====================================
    # GAME LOOP
    # =====================================
    while cmd != "quit":
        game = load_json(GAME_ROUNDS_FILE, {"current_round": 0})
        game["current_round"] += 1
        current_round = game["current_round"]
        save_json(GAME_ROUNDS_FILE, game)

        public_event(f"\n========== ROUND {current_round} ==========\n")

        night_phase()

        result = check_win_conditions()
        if result:
            public_event(result)
            break

        day_phase()

        result = check_win_conditions()
        if result:
            public_event(result)
            break

        if current_round > 20:
            break

        cmd = input("Enter=continue | quit=stop: ").strip().lower()
        if cmd == "quit":
            break

if __name__ == "__main__":
    main()
