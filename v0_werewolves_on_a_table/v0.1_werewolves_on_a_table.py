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

def log_llm(msg):
    _append(LLM_LOG_FILE, msg)

def log_llm_interaction(actor, action_type, prompt_data, raw_output, parsed_output):
    log_llm("")
    log_llm("==============================")
    log_llm(f"[{_stamp()}]")
    log_llm(f"ACTOR: {actor}")
    log_llm(f"ACTION: {action_type}")

    log_llm("")
    log_llm("--- PROMPT ---")
    try:
        log_llm(json.dumps(prompt_data, indent=2, ensure_ascii=False))
    except:
        log_llm(str(prompt_data))

    log_llm("")
    log_llm("--- RAW OUTPUT ---")
    log_llm(str(raw_output))

    log_llm("")
    log_llm("--- PARSED ---")
    try:
        log_llm(json.dumps(parsed_output, indent=2, ensure_ascii=False))
    except:
        log_llm(str(parsed_output))

    log_llm("==============================")
    log_llm("")

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

# um...internal reasoning will still be there (if parsed) even if speech/answer has issues...this is an issue...?
def parse_llm_output(raw_text, mode="speak", valid_options=None, default_speech="...", default_answer="pass"):
    if not raw_text:
        raw_text = ""

    text = str(raw_text).strip()

    # -----------------------------------
    # aliases
    # -----------------------------------
    key_alias = {
        "internal_reasoning": ["internal_reasoning", "internal reasoning", "reasoning", "thoughts", "logic", "analysis"],
        "speech": ["speech", "say", "statement", "message", "talk"],
        "answer": ["answer", "vote", "choice", "decision", "target", "selection"]
    }

    # -----------------------------------
    # helper normalize label
    # -----------------------------------
    def normalize_label(label):
        s = label.lower().strip()
        s = re.sub(r'[^a-z_ ]', '', s)
        s = re.sub(r'\s+', ' ', s)
        for canon, aliases in key_alias.items():
            for a in aliases:
                if s == a:
                    return canon
        return None

    # -----------------------------------
    # helper cleanup text
    # -----------------------------------
    def clean(v):
        v = str(v).strip()
        v = v.replace("```", "").strip()
        return v

    # -----------------------------------
    # default result
    # -----------------------------------
    result = {"internal_reasoning": ""}
    if mode == "speak":
        result["speech"] = default_speech
    else:
        result["answer"] = default_answer

    # =====================================================
    # STAGE 1: STRICT MARKER PARSE
    # label:
    # <<<
    # content
    # >>>
    # =====================================================
    marker_pattern = re.compile(
        r'(?im)^\s*([A-Za-z_ ]{2,30})\s*:\s*\n?\s*<<<\s*\n?(.*?)\n?\s*>>>',
        re.DOTALL
    )
    found = marker_pattern.findall(text)
    if found:
        parsed_any = False

        for raw_label, content in found:
            key = normalize_label(raw_label)
            if not key:
                continue

            value = clean(content)

            if value:
                result[key] = value
                parsed_any = True

        if parsed_any:
            # safe normalize answer
            if mode == "answer":
                result["answer"] = normalize_answer(result.get("answer", default_answer), valid_options, default_answer)
            return result

    # =====================================================
    # STAGE 2: LINE LABEL PARSE
    # reasoning: xxx
    # speech: xxx
    # =====================================================
    # ah...feels a bit loose/dangerous to drift here...but ok...for now...let's see.
    lines = text.splitlines()
    for line in lines:
        m = re.match(r'^\s*([A-Za-z_ ]{2,30})\s*:\s*(.+?)\s*$', line)
        if not m:
            continue

        raw_label = m.group(1)
        content = m.group(2)

        key = normalize_label(raw_label)
        if not key:
            continue

        val = clean(content)
        if val:
            result[key] = val

    # if got useful line parse
    if mode == "answer":
        result["answer"] = normalize_answer(result.get("answer", default_answer), valid_options, default_answer)
        return result
    
    if mode == "speak":
        if result.get("speech", default_speech).strip():
            return result

    # =====================================================
    # STAGE 3: CONSERVATIVE FALLBACK
    # =====================================================
    return {}

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
    
    # -------------------------------------------------
    # Build night order dynamically
    # -------------------------------------------------
    night_roles = []
    if has("seer"):
        night_roles.append("seer")
    if has("werewolf") or has("werewolves"):
        night_roles.append("werewolves")
    if has("guardian angel"):
        night_roles.append("guardian angel")
    if has("witch"):
        night_roles.append("witch")
    if has("hunter"):
        night_roles.append("hunter (if triggered)")
    night_order = " -> ".join(night_roles)

    # -------------------------------------------------
    # Build numbered role rules dynamically
    # -------------------------------------------------
    steps = []
    n = 1
    if has("seer"):
        steps.append(
            f"{n}. Seer:\n"
            "   - May inspect one living player.\n"
            "   - Learns only the target's team (Werewolf or Village), not role."
        )
        n += 1
    if has("werewolf") or has("werewolves"):
        steps.append(
            f"{n}. Werewolves:\n"
            "   - See other werewolves; know teammates.\n"
            "   - Hold at most three rounds of private discussion.\n"
            "   - Discussion may end early if all alive werewolves agree to vote now.\n"
            "   - Then vote once to select a target.\n"
            "   - Highest votes selects target.\n"
            "   - Tie = no target.\n"
            "   - May choose no target or self-target."
        )
        n += 1
    if has("guardian angel"):
        steps.append(
            f"{n}. Guardian Angel:\n"
            "   - May protect one living player.\n"
            "   - Cannot protect same player on consecutive nights.\n"
            "   - Protection only invalidates werewolf targeting."
        )
        n += 1
    if has("witch"):
        steps.append(
            f"{n}. Witch:\n"
            "   - Has one save potion and one poison potion, each usable once per game.\n"
            "   - Learns werewolf target result.\n"
            "   - If there's a valid target, may cancel the targeting with the save potion.\n"
            "   - May poison one living player with the poison potion."
        )
        n += 1
    if has("hunter"):
        steps.append(
            f"{n}. Hunter:\n"
            "   - Triggers only if still targeted by werewolves validly.\n"
            "   - May shoot one living player.\n"
            "   - Still targeted by werewolves."
        )
        n += 1
    night_steps = "\n".join(steps)

    night_resolution = []
    # Always include werewolf target
    night_resolution.append("Werewolf target (if still valid)")
    if has("witch"):
        night_resolution.append("Witch poison")
    if has("hunter"):
        night_resolution.append("Hunter shot")
    night_resolution_str = " -> ".join(night_resolution)

    # -------------------------------------------------
    # Day interrupt rules dynamically
    # -------------------------------------------------
    interrupts = []
    if has("knight"):
        interrupts.append(
            "- Knight (once per game, on own speaking turn):\n"
            "  * May challenge one living player.\n"
            "  * If target is werewolf, target dies.\n"
            "  * Otherwise both die.\n"
            "  * Discussion ends immediately.\n"
            "  * No vote occurs."
        )
    if has("werewolf") or has("werewolves"):
        interrupts.append(
            "- Werewolf:\n"
            "  * May reveal themselves publicly.\n"
            "  * Dies immediately.\n"
            "  * Discussion ends immediately.\n"
            "  * No vote occurs."
        )
    interrupt_text = "\n".join(interrupts) if interrupts else "- No special interrupts in this game."

    # -------------------------------------------------
    # Final text
    # -------------------------------------------------
    text = f"""
Game setup: {player_number} players are assigned the roles of {roles}.
Each player receives one fixed role.

Werewolves are Team Werewolf.
All others are Team Village.

Win conditions:
- Werewolves win if all Village players are dead.
- Village wins if all Werewolves are dead.
- If all players die, the game is a tie.

All players follow these rules:
- No one knows others' roles at the start except werewolves know teammates.
- Claims are not automatically reliable.

Game phases:
- The game starts at night.
- Night phase action order: {night_order}
- Day phase: two rounds of open discussion, then voting.

General rules:
- Actions/votes target living players unless stated otherwise.
- Dead players cannot act, speak, vote, or be targeted.

Night phase:
- Non-acting players are inactive.
- Roles act in order:

{night_steps}

Night resolution:
- Death order:
{night_resolution_str}
- Deaths apply together at end of night.

Day phase:
- Morning announces deaths by player name only.
- Two rounds of public discussion.
- Speaking order is randomized.
- Everyone can hear everyone.

Interrupt actions during discussion:
{interrupt_text}

- If no interrupt occurs:
- All living players vote once.
- May vote living player, self, or abstain.
- Most votes = eliminated.
- Tie = no elimination.

The game alternates night/day until a win condition is met.

Team objectives:
- Werewolves eliminate Village.
- Village eliminate Werewolves.
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
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
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
        RECENT_MEMORY_COUNTER[name] = 1

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

def build_llm_view(chars, actor_name):
    actor = chars["characters"][actor_name]
    game = load_json(GAME_ROUNDS_FILE, game_round_template())

    view = {
        "name": actor_name,
        "gender": actor["gender"],
        "age_apparent": actor["age_apparent"],
        "age_actual": actor["age_actual"],

        "appearance": actor["appearance"],
        "personality": actor["personality"],

        "goals": actor["goals"],
        "mental_state": actor["mental_state"],
        "ongoing_processes": actor["ongoing_processes"],

        "memory": actor.get("memory", {}),

        "knowledge": {
            "scene": {
                "location": actor["knowledge"]["scene"]["location"],
                "environment": actor["knowledge"]["scene"]["environment"],
                "rules": actor["knowledge"]["scene"]["rules"],
                "characters_present": actor["knowledge"]["scene"]["characters_present"]
            },
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

    view["game_status"]["current_round"] = game.get("current_round",0)

    for name, target in chars["characters"].items():
        if name == actor_name:
            continue
        view["knowledge"]["characters"][name] = {
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
    
    return prune_empty(view)

# =========================
# CALL LLM
# =========================
def system_prompt_rules():
    rules = """
You are simulating a character in a structured social deduction game.

Rules:
- Use ONLY information in the input. Do NOT invent or assume facts.
- Stay consistent with the character's personality, goals and knowledge.
- MAY use memory, but do NOT recap memory unless directly useful. Use memory only as brief evidence for current decisions.
- When information is limited, DO NOT overthink. Make the decision, even if imperfect.
- BE concise, strategic, and relevant. NO filler, repetition, hedging, or empty statements.
- Output MUST be compressed, obeying WORD LIMITS. EXCESS will be TRUNCATED.

Output:
- Internal reasoning summary of the character, MAXIMUM 50 words.
"""
    return rules.strip()

def system_prompt_speak():
    speak = f"""
{system_prompt_rules()}
- Speech to others, MAXIMUM 50 words.

Return EXACTLY this format:

internal_reasoning:
<<<
your reasoning
>>>

speech:
<<<
your speech
>>>

No extra text.
"""
    return speak.strip()

def system_prompt_answering():
    vote = f"""
{system_prompt_rules()}
- Select ONE answer from the provided valid options. Any answer not in valid options will count as pass.

Return EXACTLY this format:

internal_reasoning:
<<<
your reasoning
>>>

answer:
<<<
your selected option
>>>

No extra text.
"""
    return vote.strip()

def build_payload_speak(character_information, phase_step, reminder="", extras=None):
    payload = {
        "character_information": character_information,
        "phase_step": phase_step,
        "reminder": reminder
    }
    if extras:
        payload.update(extras)

    return payload

def build_payload_answer(character_information, phase_step, question, valid_options, reminder="", extras=None):
    payload = {
        "character_information": character_information,
        "phase_step": phase_step,
        "reminder": reminder,
        "question": question,
        "valid_options": valid_options
    }
    if extras:
        payload.update(extras)

    return payload

def call_llm(actor_name, model_name, sys_prompt, user_payload, 
    call_type="speech", valid_options=None, default_answer="pass", default_speech="...", max_len=500
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
    time.sleep(3)

    # =====================================================
    # SPEECH MODE
    # =====================================================
    if call_type == "speech":
        data = parse_llm_output(raw_text=raw_content, mode="speak", default_speech=default_speech)
        
        speech = data.get("speech", default_speech)[:max_len]
        if speech != default_speech:
            internal_reasoning = data.get("internal_reasoning", "")[:max_len]
        else:
            internal_reasoning = ""
        
        result = {
            "internal_reasoning": internal_reasoning,
            "speech": speech,
            "raw_content": raw_content
        }

        log_llm_interaction(actor_name, call_type, sys_prompt+"\n"+user_payload, raw_content,
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
            internal_reasoning = data.get("internal_reasoning", "")[:max_len]
        else:
            internal_reasoning = ""
        
        result = {
            "internal_reasoning": internal_reasoning,
            "answer": answer,
            "raw_content": raw_content
        }

        log_llm_interaction(actor_name, call_type, sys_prompt+"\n"+user_payload, raw_content,
            {
                "normalized_answer": result["answer"],
                "internal_reasoning": result["internal_reasoning"]
            }
        )

        return result

# =========================
# MEMORY HELPERS
# =========================
# WORDS/CHARS LIMIT ISSUE - CHARS?!! WORDS?!! INCONSISTENT. FORCED TRUNCATE. PROBLEMS???
def summarize_single_field(field_name, text, word_limit):
    prompt = f"""
        Summarize this {field_name} briefly.

        Rules:
        - Preserve names.
        - Preserve intent.
        - Max {word_limit} words.
        - No invented facts.

        Return only plain text.
    """
    try:
        response = client.chat.completions.create(
            model=random.choice(MODEL_SMALL),
            messages=[
                {"role":"system","content":prompt},
                {"role":"user","content":text}
            ]
        )

        content = response.choices[0].message.content.strip()

        log_llm_interaction("", "summarize_single_field", "", text, content)

        return content
    
    except:
        return text.strip()

# ALL NEEDS STRICT INSERT TIMELINE!!! WARNING!!!
RECENT_MEMORY_COUNTER = {}
def trim_recent_memory(char, counter, 
    keep_latest=6, base_max_chars=1200, decay_step=200, floor_chars=200
):
    """
    Re-trim ALL recent memory units outside newest keep_latest.
    Example:
    total = 18
    newest 6  -> untouched
    middle 6  -> limit = 1200 - 1*200
    oldest 6  -> limit = 1200 - 2*200
    Runs only when: counter % 6 == 0 and counter // 6 > 1
    """

    recent = char.get("memory", {}).get("recent", {})
    if not isinstance(recent, dict):
        return False

    # trigger every +6 after first block
    if counter % keep_latest != 0:
        return False

    wave = counter // keep_latest
    if wave <= 1:
        return False

    # ---------------------------------
    # flatten full timeline
    # oldest -> newest
    # ---------------------------------
    timeline = []
    for bucket_key, bucket in recent.items():
        if not isinstance(bucket, list):
            continue

        for idx, mem in enumerate(bucket):
            if isinstance(mem, dict):
                timeline.append((bucket_key, idx, mem))

    total = len(timeline)
    if total <= keep_latest:
        return False

    changed_any = False
    # ---------------------------------
    # trim everything except newest 6
    # ---------------------------------
    trim_count = total - keep_latest
    for pos in range(trim_count):
        bucket_key, idx, mem = timeline[pos]

        # group depth:
        # oldest six = deeper trim
        # next six = less trim
        # total=18:
        # pos 0-5  -> depth 2
        # pos 6-11 -> depth 1

        remaining_from_trim_end = trim_count - pos - 1
        depth = (remaining_from_trim_end // keep_latest) + 1
        max_chars = max(base_max_chars - depth * decay_step, floor_chars)

        content = mem.get("content", {})
        if not isinstance(content, dict):
            continue

        changed = False
        new_content = {}
        for field_name, value in content.items():
            if isinstance(value, str) and len(value) > max_chars:
                new_content[field_name] = summarize_single_field(field_name, value, max_chars//10)[:max_chars]
                changed = True
            else:
                new_content[field_name] = value

        if changed:
            mem["content"] = new_content
            meta = mem.setdefault("metadata", {})
            meta["impact"] = max(5, meta.get("impact", 50) - 5)
            meta["confidence"] = max(5, meta.get("confidence", 50) - 10)

            recent[bucket_key][idx] = mem
            changed_any = True

    return changed_any

def filter_other_speech_with_llm(text, word_limit):
    """
    Keep only strategically useful information from OTHER people's speeches.
    Return short note string, or None if discard.
    """

    prompt = f"""
        You are filtering memory from a social deduction game speech.

        Keep ONLY if the speech contains CLEAR useful signals such as:
        1. suspicion / accusation of a named player
        2. defense / trust of a named player
        3. role inference / role claim
        4. voting intention
        5. contradiction / strategic statement
        6. concrete alliance signal

        Return ONLY such signals. Discard all other vague filler, emotion, repetition, noise.

        Rules:
        - Preserve names exactly.
        - No invented facts.
        - Max {word_limit} words.
        - If nothing useful, return DROP

        Return plain text only.
    """
    try:
        response = client.chat.completions.create(
            model=random.choice(MODEL_SMALL),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ]
        )

        out = response.choices[0].message.content.strip()

        log_llm_interaction("", "filter_other_speech_with_llm", "", text, out)

        if not out:
            return None
        if out.upper() == "DROP":
            return None
        
        return out
    
    except:
        # safe fallback = discard
        return None
    
def archive_recent_to_mid(char, current_round):
    """
    End-of-round pipeline
    1. Compress remaining recent snippets if long (???) (needed???) (removed)
    2. recent -> mid[game_round_X]
    3. Preserve timeline order
    4. Clear recent
    """

    memory = char.setdefault("memory", {})
    recent = memory.setdefault("recent", {})
    mid = memory.setdefault("mid", {})

    if not recent:
        return

    # =====================================
    # STEP 2: build round block
    # =====================================
    round_key = f"game_round_{current_round}"
    round_block = {
        "self": {},
        "perceives": {},
        "announcement": {}
    }

    # =====================================
    # STEP 3: route by true timeline
    # =====================================
    for bucket_key, bucket in recent.items():
        if not isinstance(bucket, list):
            continue

        for mem in bucket:
            if not isinstance(mem, dict):
                continue

            source_type = mem.get("source_type", "")
            phase_step = mem.get("phase_step", "unknown")
            content = mem.get("content", {})
            meta = mem.get("metadata", {})

            if not isinstance(content, dict):
                continue

            performer = content.get("performer", "")
            impact = meta.get("impact", 50)
            confidence = meta.get("confidence", 100)

            # payload = content except performer
            payload = {}
            for k, v in content.items():
                if k == "performer":
                    continue

                # speech filter only for others
                if k == "speech" and source_type != "self":
                    filtered = filter_other_speech_with_llm(str(v), len(v)//10)[:len(v)]
                    if filtered:
                        payload["speech"] = filtered
                    continue
                payload[k] = v

            # =================================
            # SELF
            # =================================
            if source_type == "self":
                round_block["self"].setdefault(phase_step, [])

                row = dict(payload)
                row["impact"] = impact
                row["confidence"] = confidence

                round_block["self"][phase_step].append(row)

            # =================================
            # ANNOUNCEMENT
            # =================================
            elif performer == "announcement":
                round_block["announcement"].setdefault(phase_step, [])

                row = dict(payload)
                row["impact"] = impact
                row["confidence"] = confidence

                round_block["announcement"][phase_step].append(row)

            # =================================
            # PERCEIVES
            # =================================
            else:
                if not performer:
                    performer = "unknown"

                round_block["perceives"].setdefault(performer, {})
                round_block["perceives"][performer].setdefault(phase_step, [])

                row = dict(payload)
                row["impact"] = impact
                row["confidence"] = confidence

                round_block["perceives"][performer][phase_step].append(row)

    # =====================================
    # STEP 4: save
    # =====================================
    mid[round_key] = round_block

    # =====================================
    # STEP 5: clear recent
    # =====================================
    memory["recent"] = {}

def get_mid_char_limit(bucket_type, age):
    """
    bucket_type:
        self / perceives / announcement
    """

    HARD_FLOOR = 140

    if bucket_type == "self":
        base = 500
        decay = 60
        floor = 180

    elif bucket_type == "announcement":
        base = 320
        decay = 20
        floor = 180

    else:  # perceives
        base = 220
        decay = 35
        floor = 140

    floor = max(floor, HARD_FLOOR)

    return max(base - age * decay, floor)

def trim_mid_memory(char, current_round):
    """
    Compress old mid memory after each round.

    Uses:
    - filter_other_speech_with_llm() for others' speeches
    - summarize_single_field() for everything else

    Keeps all round keys.
    No deletions.
    """

    memory = char.get("memory", {})
    mid = memory.get("mid", {})

    if not isinstance(mid, dict):
        return False

    changed_any = False

    for round_key, round_block in mid.items():
        # -----------------------------
        # parse round number
        # -----------------------------
        try:
            round_num = int(str(round_key).replace("game_round_", ""))
        except:
            continue

        age = current_round - round_num
        # a bit "missed" below...? but ok...? since the order in the main function...?
        if age <= 0:
            continue   # newest round untouched

        # =====================================================
        # SELF
        # =====================================================
        self_limit = get_mid_char_limit("self", age)
        self_bucket = round_block.get("self", {})
        for phase_step, entries in self_bucket.items():
            if not isinstance(entries, list):
                continue

            for item in entries:
                if not isinstance(item, dict):
                    continue

                for field, value in list(item.items()):
                    if field in ["impact", "confidence"]:
                        continue

                    if not isinstance(value, str):
                        continue

                    if len(value) > self_limit:
                        max_words = max(8, self_limit // 10)
                        item[field] = summarize_single_field(field, value, max_words)[:self_limit]
                        changed_any = True

                item["impact"] = max(5, item.get("impact", 50) - 5)
                item["confidence"] = max(5, item.get("confidence", 50) - 10)

        # =====================================================
        # PERCEIVES
        # =====================================================
        perceive_limit = get_mid_char_limit("perceives", age)
        perceive_bucket = round_block.get("perceives", {})
        for actor, actor_block in perceive_bucket.items():
            if not isinstance(actor_block, dict):
                continue

            for phase_step, entries in actor_block.items():
                if not isinstance(entries, list):
                    continue

                for item in entries:
                    if not isinstance(item, dict):
                        continue

                    for field, value in list(item.items()):
                        if field in ["impact", "confidence"]:
                            continue

                        if not isinstance(value, str):
                            continue

                        # speeches use filter
                        if field == "speech":
                            if len(value) > perceive_limit:
                                filtered = filter_other_speech_with_llm(value, perceive_limit//10)
                                if filtered:
                                    item[field] = filtered[:perceive_limit]
                                else:
                                    item[field] = ""
                                changed_any = True

                        else:
                            if len(value) > perceive_limit:
                                max_words = max(6, perceive_limit // 10)
                                item[field] = summarize_single_field(field, value, max_words)[:perceive_limit]
                                changed_any = True

                    item["impact"] = max(5, item.get("impact", 50) - 5)
                    item["confidence"] = max(5, item.get("confidence", 50) - 10)

        # =====================================================
        # ANNOUNCEMENT
        # =====================================================
        ann_limit = get_mid_char_limit("announcement", age)
        ann_bucket = round_block.get("announcement", {})
        for phase_step, entries in ann_bucket.items():
            if not isinstance(entries, list):
                continue

            for item in entries:
                if not isinstance(item, dict):
                    continue

                for field, value in list(item.items()):
                    if field in ["impact", "confidence"]:
                        continue

                    if not isinstance(value, str):
                        continue

                    if len(value) > ann_limit:
                        max_words = max(8, ann_limit // 10)
                        item[field] = summarize_single_field(field, value, max_words)[:ann_limit]
                        changed_any = True

                item["impact"] = max(5, item.get("impact", 50) - 2)
                item["confidence"] = max(5, item.get("confidence", 50) - 2)

    return changed_any

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

def ask_llm_for_target(actor_name, action_type, action_target):
    chars = load_json(CHARACTERS_FILE, {"characters": {}})
    game_round = load_json(GAME_ROUNDS_FILE, {})
    view = build_llm_view(chars, actor_name)

    # ---- question ----
    if action_type == "seer":
        question = "You are the Seer. Which player do you want to inspect tonight?"

    elif action_type == "guardian_angel":
        question = "You are the Guardian Angel. Which player do you want to protect tonight? (you cannot protect the same player as last night)"

    elif action_type == "witch_save":
        question = f"You are the Witch. The player '{action_target}' is going to die tonight. Do you want to use your save potion?"

    elif action_type == "witch_poison":
        question = "You are the Witch. Which player do you want to poison tonight, or choose no one?"

    elif action_type == "hunter":
        question = "You are the Hunter. You are going to die tonight. Which player do you want to shoot? or no one?"

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
        reminder="make the best decision you deem, help your team win the game"
    )
    model = chars["characters"][actor_name]["llm_model"]

    result = call_llm(actor_name, model, SYSTEM_PROMPT, payload, "answer", valid_range_of_selection)
    answer = result.get("answer", "pass")
    internal_reasoning = result.get("internal_reasoning", "")

    # ---- use output ----
    mem_snippet = {
        "memory_owner": actor_name,
        "source_type": "self",
        "phase_step": f"night_action_{action_type}",
        "content": {
            "performer": actor_name,
            "action": f"answered '{answer}' to the question '{question}'",
            "internal_reasoning": internal_reasoning
        },
        "metadata":{
            "impact": 100,
            "confidence": 100
        }
    }
    current_round = game_round.get("current_round", 0)
    chars["characters"][actor_name]["memory"]["recent"].setdefault(f"round_{current_round}_night_{action_type}",[]).append(mem_snippet)
    
    RECENT_MEMORY_COUNTER[actor_name] = RECENT_MEMORY_COUNTER.get(actor_name,0)+1
    trim_recent_memory(chars["characters"][actor_name], RECENT_MEMORY_COUNTER[actor_name])
    
    save_json(CHARACTERS_FILE, chars)

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
    SYSTEM_PROMPT_DISCUSSION = system_prompt_speak()

    # =====================================
    # 3 ROUNDS PRIVATE DISCUSSION
    # =====================================
    for discuss_round in range(1, 4):
        for speaker in speak_order:
            # skip dead during phase (future-proof)
            if chars["characters"][speaker]["game_status"]["is_dead"]:
                continue

            view = build_llm_view(chars, speaker)
            payload = build_payload_speak(
                view,
                f"night_wolfchat_round_{discuss_round}",
                reminder="Coordinate with werewolves to determine the target to kill tonight"
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
            
            RECENT_MEMORY_COUNTER[speaker] = RECENT_MEMORY_COUNTER.get(speaker,0)+1
            trim_recent_memory(chars["characters"][speaker], RECENT_MEMORY_COUNTER[speaker])

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
                
                RECENT_MEMORY_COUNTER[listener] = RECENT_MEMORY_COUNTER.get(listener,0)+1
                trim_recent_memory(chars["characters"][listener], RECENT_MEMORY_COUNTER[listener])

            save_json(CHARACTERS_FILE, chars)
        
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
            reminder="Vote effectively and help Team Werewolf win the game"
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

        RECENT_MEMORY_COUNTER[wolf] = RECENT_MEMORY_COUNTER.get(wolf,0)+1
        trim_recent_memory(chars["characters"][wolf], RECENT_MEMORY_COUNTER[wolf])

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
            
            RECENT_MEMORY_COUNTER[observer] = RECENT_MEMORY_COUNTER.get(observer,0)+1
            trim_recent_memory(chars["characters"][observer], RECENT_MEMORY_COUNTER[observer])

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
                "announcement": f"votes: {votes}; final_kill_target_tonight: {result if result else 'no_kill'}"
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][wolf]["memory"]["recent"].setdefault(
            f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)

        RECENT_MEMORY_COUNTER[wolf] = RECENT_MEMORY_COUNTER.get(wolf,0)+1
        trim_recent_memory(chars["characters"][wolf], RECENT_MEMORY_COUNTER[wolf])

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
        target = ask_llm_for_target_wolves(wolves)

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
            if use_save == "yes":
                night_state["werewolf_target"] = None
                ability["save_potion"] -= 1
                save_json(CHARACTERS_FILE, chars)

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
    
    # LOGGING
    public_event(announcement_text)

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
            "phase_step": "morning_announcement",
            "content": {
                "performer": "announcement",
                "announcement": announcement_text
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        char["memory"]["recent"].setdefault(
            f"round_{current_round}_morning_announcement",[]).append(mem_snippet)
        
        RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
        trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

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
        reminder="If your target isn't a werewolf, you BOTH DIE. Use ONLY if it's worth the risk."
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

        RECENT_MEMORY_COUNTER[speaker] = RECENT_MEMORY_COUNTER.get(speaker,0)+1
        trim_recent_memory(chars["characters"][speaker], RECENT_MEMORY_COUNTER[speaker])
        
        save_json(CHARACTERS_FILE, chars)
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
        
        RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
        trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

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
                "announcement": f"{answer} {', '+speaker if result == 'both_dead' else ''} died due to knight challenge; the day ends here"
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        })
        RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
        trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

    save_json(CHARACTERS_FILE, chars)
    return True

def wolf_reveal(chars, speaker, view, current_round):
    SYSTEM_PROMPT_REVEAL = system_prompt_answering()

    payload = build_payload_answer(
        view,
        "day_werewolf_reveal",
        question="Reveal yourself publicly?",
        valid_options=["yes", "no"],
        reminder="Your reveal will kill you, end the discussion and skip the vote. Reveal ONLY if you decide it STRONGLY helps werewolves."
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
            RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
            trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

            c["memory"]["recent"].setdefault(f"round_{current_round}_day_wolf_reveal", []).append({
                "memory_owner": name,
                "source_type": "heard",
                "phase_step": "day_wolf_reveal",
                "content": {
                    "performer": "announcement",
                    "announcement": f"{speaker}, the werewolf, died due to self-reveal; the day ends here"
                },
                "metadata": {
                    "impact": 100,
                    "confidence": 100
                }
            })
            RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
            trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

        save_json(CHARACTERS_FILE, chars)
        return True   # interrupt triggered

    # =====================================
    # NO = private self memory only
    # =====================================
    else:
        mem = {
            "memory_owner": speaker,
            "source_type": "self",
            "phase_step": "day_wolf_reveal_decision",
            "content": {
                "performer": speaker,
                "action": "did not reveal",
                "internal_reasoning": internal_reasoning
            },
            "metadata": {
                "impact": 60,
                "confidence": 100
            }
        }
        chars["characters"][speaker]["memory"]["recent"].setdefault(f"round_{current_round}_day_wolf_reveal_decision", []).append(mem)
        
        RECENT_MEMORY_COUNTER[speaker] = RECENT_MEMORY_COUNTER.get(speaker,0)+1
        trim_recent_memory(chars["characters"][speaker], RECENT_MEMORY_COUNTER[speaker])

        save_json(CHARACTERS_FILE, chars)
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
            payload = build_payload_speak(
                view,
                f"day_public_discussion_round_{discuss_round}",
                reminder="You're discussing who to eliminate today. You may accuse, defend, suspect, persuade, or test reactions"
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

            RECENT_MEMORY_COUNTER[speaker] = RECENT_MEMORY_COUNTER.get(speaker,0)+1
            trim_recent_memory(chars["characters"][speaker], RECENT_MEMORY_COUNTER[speaker])

            # ---------------------------------
            # OTHERS HEAR SPEECH
            # ---------------------------------
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

                RECENT_MEMORY_COUNTER[listener] = RECENT_MEMORY_COUNTER.get(listener,0)+1
                trim_recent_memory(chars["characters"][listener], RECENT_MEMORY_COUNTER[listener])

            save_json(CHARACTERS_FILE, chars)

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

        payload = build_payload_answer(
            view,
            "day_public_vote",
            question="Who do you vote to eliminate today?",
            valid_options=valid_options,
            reminder="Your objective is to help your team win the game. Evaluate risk and consider carefully."
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

        RECENT_MEMORY_COUNTER[voter] = RECENT_MEMORY_COUNTER.get(voter,0)+1
        trim_recent_memory(chars["characters"][voter], RECENT_MEMORY_COUNTER[voter])

        # ---------------------------------
        # OTHERS OBSERVE VOTE
        # ---------------------------------
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

            RECENT_MEMORY_COUNTER[observer] = RECENT_MEMORY_COUNTER.get(observer,0)+1
            trim_recent_memory(chars["characters"][observer], RECENT_MEMORY_COUNTER[observer])

        save_json(CHARACTERS_FILE, chars)

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
                "announcement": f"votes: {votes}; eliminated_player: {eliminated if eliminated else 'None'}"
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        }
        char["memory"]["recent"].setdefault(
            f"round_{current_round}_day_vote", []).append(mem_snippet)

        RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
        trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

        if eliminated:
            char["knowledge"]["characters"][eliminated]["game_status"]["is_dead"] = {
                "value": True, "confidence": 100}

    # LOGGING
    public_event(f"\nLynch Decision\n{votes}\n{eliminated}\n")

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
    ALL_CHARACTER_NAMES = [
        "AA", "GA", "MA", "PA", "SA", "VA", "YA",
        "CX", "DX", "FX", "LX", "NX", "TX", "WX", 
    ]
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

    # =====================================
    # FLEXIBLE ROLE
    # =====================================
    flexible_role = None
    if player_number == 7:
        valid_flex = POWER_ROLES[:]   # seer already fixed
    elif player_number == 10:
        valid_flex = ["hunter", "knight", "guardian_angel"]  # seer + witch fixed
    else:
        valid_flex = []

    if valid_flex:
        while True:
            print(f"Choose flexible role: {', '.join(valid_flex)}")
            raw = input("Flexible role: ").strip().lower()
            if raw in valid_flex:
                flexible_role = raw
                break
            print("Invalid choice.")
    
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
    public_event("------INITIALIZATION FINISHED------")

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

        chars = load_json(CHARACTERS_FILE, {"characters": {}})
        for char in chars["characters"].values():
            trim_mid_memory(char, current_round)
            archive_recent_to_mid(char, current_round)

        RECENT_MEMORY_COUNTER.clear()
        save_json(CHARACTERS_FILE, chars)

        if current_round > 20:
            break

        cmd = input("Enter=continue | quit=stop: ").strip().lower()
        if cmd == "quit":
            break

if __name__ == "__main__":
    main()
