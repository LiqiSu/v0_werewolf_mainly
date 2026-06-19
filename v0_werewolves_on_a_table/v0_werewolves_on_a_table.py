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
import difflib

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    API_KEY = getpass.getpass("GROQ API key: ").strip()

MODEL = "llama-3.3-70b-versatile"

DATA_DIR = "data"
WORLD_BIBLE_FILE = os.path.join(DATA_DIR, "world_bible.json")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.json")
SCENE_STATE_FILE = os.path.join(DATA_DIR, "scene_state.json")
GAME_ROUNDS_FILE = os.path.join(DATA_DIR, "game_rounds.json")

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
# LOGGING SYSTEM: BUUGGG AND INCOMPLETE
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

def log(msg):
    line = f"[{_stamp()}] {msg}"
    print(line)
    _append(DEBUG_LOG_FILE, line)

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
def normalize_choice(answer, valid_options):
    if answer is None:
        return None

    text = str(answer).strip()

    if not text:
        return None

    lower = text.lower()

    # exact match
    for opt in valid_options:
        if lower == str(opt).lower():
            return opt

    # contains match
    for opt in valid_options:
        if str(opt).lower() in lower:
            return opt

    # fuzzy close match
    candidates = difflib.get_close_matches(
        lower,
        [str(x).lower() for x in valid_options],
        n=1,
        cutoff=0.75
    )
    if candidates:
        chosen = candidates[0]
        for opt in valid_options:
            if str(opt).lower() == chosen:
                return opt

    return None

# UMMMM...NOT USED FOR NOW...LET'S SEE FIRST
# BUT IMPORTANT!!! ABSOLUTELY!!!
def parse_json_response(raw_text, fallback=None):
    if fallback is None:
        fallback = {}

    if not raw_text:
        return fallback

    text = raw_text.strip()

    # remove code fences
    text = text.replace("```json", "").replace("```", "").strip()

    # find first {...}
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        return json.loads(text)
    except:
        return fallback

def extract_braced_text(text, fallback=""):
    if not text:
        return fallback

    match = re.search(r'\{(.*?)\}', text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return fallback

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

def game_rule():
    return {
        "Werewolves_Table": {
            "description": (
                "Game setup: 14 players are assigned the roles of 4 werewolves, 5 villagers, 1 seer, 1 witch, 1 hunter, 1 knight, and 1 guardian angel.\n"
                "Each player receives one role; the role is fixed throughout the game.\n"
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

                "Night phase:\n"
                "- All players cannot perceive, speak, or act.\n"
                "- Then player(s) with the corresponding role(s) executes the following actions in order.\n"
                "- After each action, the player(s) resumes the inactive state:\n"
                "1. Seer:\n"
                "   - May choose to inspect one living player.\n"
                "   - Learns only the target's team (Werewolf or Village), not role.\n"
                "2. Werewolves:\n"
                "   - See other werewolves; know their teammates.\n"
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

                "Day phase:\n"
                "- Day begins with the morning announcement of all deaths (players' names only, no roles or causes).\n"
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
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        return data.get("personality", {})
    except Exception as e:
        log_error("generate_personality_with_llm", e)

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
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
        return data.get("appearance", {})
    except Exception as e:
        log_error("generate_appearance_with_llm", e)

def initialize_characters(CHARACTER_NAMES, IF_INITIAL_TRAITS=False):
    # chars = {"characters": {}}
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

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
        char = chars["characters"][name]
        # char = character_template()
        # =================initial traits====================
        if IF_INITIAL_TRAITS:
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
        # ====================================================
        
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
        content = response.choices[0].message.content
        return content
    except Exception as e:
        log_error("summarize_appearance_with_llm", e)

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

    # appearance here: the key's fixed by me. note. hard-coded stuff.
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
        "species": actor["species"],

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
            model=MODEL,
            messages=[
                {"role":"system","content":prompt},
                {"role":"user","content":text}
            ]
        )
        return response.choices[0].message.content.strip()
    
    except:
        return text.strip()

# ALL NEEDS STRICT INSERT TIMELINE!!! WARNING!!!
RECENT_MEMORY_COUNTER = {}
def trim_recent_memory(char, counter, keep_latest=6, base_max_chars=1200, decay_step=200, floor_chars=200):
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
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ]
        )

        out = response.choices[0].message.content.strip()

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
        - You MUST NOT assume, invent, or hallucinate any information not presented.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to reason and deduct.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 120 words, any excess will be truncated.
        - Then provide a final answer to the question asked.
        - you MUST provide an answer within the given VALID range of selection, otherwise your answer will be considered as "no action".

        Return STRICT JSON in this format:
        {
        "internal_reasoning": "",
        "answer": "",
        }
    """
    if action_type in ["seer", "witch_poison", "hunter"]:
        valid_range_of_selection = get_valid_targets(chars, exclude=[])
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

        raw_content = response.choices[0].message.content
        content = raw_content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)

        raw_answer = data.get("answer")
        internal_reasoning = data.get("internal_reasoning", "")[:1200]

        answer = normalize_choice(raw_answer, valid_range_of_selection)

        if answer is None:
            log(f"{actor_name} invalid choice '{raw_answer}' -> no action")

        else:
            log(f"{actor_name} chose {answer}")

        parsed = {
            "raw_answer": raw_answer,
            "normalized_answer": answer,
            "internal_reasoning": internal_reasoning
        }
        log_llm_interaction(actor_name, action_type, "", raw_content, parsed)

    except Exception as e:
        answer = None
        internal_reasoning = ""
        log_error(f"ask_llm_for_target {actor_name}", e)

    # ---- use output ----
    mem_snippet = {
        "memory_owner": actor_name,
        "source_type": "self",
        "phase_step": f"night_action_{action_type}",
        "content": {
            "performer": actor_name,
            "action": f"answered '{answer}' to the question '{question}'" if answer else "no action",
            "internal_reasoning": internal_reasoning if answer else ""
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
        - You MUST NOT assume, invent, or hallucinate any information not presented.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to reason and speak.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 120 words.
        - Then present your speech to other werewolves; the MAXIMUM length is 120 words, any excess will be truncated.
        - Be PRECISE and CONCISE.

        Return STRICT JSON in this format:
        {
        "internal_reasoning": "",
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
            valid_targets = get_valid_targets(chars, exclude=[])
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

                raw_content = response.choices[0].message.content
                content = raw_content.replace("```json", "").replace("```", "").strip()
                data = json.loads(content)

                internal_reasoning = data.get("internal_reasoning", "")[:1200]
                speech = data.get("speech", "")[:1200]

                parsed = {
                    "speech": speech,
                    "internal_reasoning": internal_reasoning
                }
                log_llm_interaction(speaker, "wolfchat", "", raw_content, parsed)
            except Exception as e:
                internal_reasoning = ""
                speech = "..."
                log_error(f"wolf_chat_round_{discuss_round}", e)

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
            chars["characters"][speaker]["memory"]["recent"].setdefault(f"round_{current_round}_night_wolfchat_round_{discuss_round}",[]).append(mem_snippet)
            
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
                chars["characters"][listener]["memory"]["recent"].setdefault(f"round_{current_round}_night_wolfchat_round_{discuss_round}",[]).append(mem_snippet)
                
                RECENT_MEMORY_COUNTER[listener] = RECENT_MEMORY_COUNTER.get(listener,0)+1
                trim_recent_memory(chars["characters"][listener], RECENT_MEMORY_COUNTER[listener])

            save_json(CHARACTERS_FILE, chars)

    # =====================================
    # VOTING PHASE
    # =====================================
    SYSTEM_PROMPT_VOTE = """
        You are simulating a character in a structured social deduction game.
        Your character's role is werewolf, you've discussed with other werewolves, now it's time to decide and vote on a target to kill tonight.

        Rules:
        - You MUST only use the information provided in the input.
        - You MUST NOT assume, invent, or hallucinate any information not presented.
        - You MUST behave consistently with the character's personality, goals, and knowledge.
        - You may reference information presented in your memory.
        - You MUST use ONLY the presented information to decide and vote.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; the MAXIMUM length is 120 words, any excess will be truncated.
        - Then provide your final vote decision for the target to kill tonight. 
        - your vote decision MUST be within the given target range, otherwise it will be counted as "no_kill".

        Return STRICT JSON in this format:
        {
        "internal_reasoning": "",
        "vote": ""
        }
    """
    votes = {}
    for wolf in wolves:
        if chars["characters"][wolf]["game_status"]["is_dead"]:
            continue

        view = build_llm_view(chars, wolf)
        valid_targets = get_valid_targets(chars, exclude=[])
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

            raw_content = response.choices[0].message.content
            content = raw_content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

            internal_reasoning = data.get("internal_reasoning", "")[:1200]
            raw_vote = data.get("vote")
            answer = normalize_choice(raw_vote, valid_vote_options)
            
            parsed = {
                "raw_answer": raw_vote,
                "normalized_answer": answer,
                "internal_reasoning": internal_reasoning
            }
            log_llm_interaction(wolf, "wolfchat_vote", "", raw_content, parsed)
        except Exception as e:
            internal_reasoning = ""
            answer = "no_kill"
            log_error("wolfchat_vote", e)

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
                "action": f"voted for {answer} as the target to kill tonight" if answer and answer != "no_kill" else "voted for no_kill",
                "internal_reasoning": internal_reasoning if answer else ""
            },
            "metadata":{
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][wolf]["memory"]["recent"].setdefault(f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)

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
                    "action": f"voted for {answer} as the target to kill tonight" if answer and answer != "no_kill" else "voted for no_kill",
                },
                "metadata":{
                    "impact": 90,
                    "confidence": 100
                }
            }
            chars["characters"][observer]["memory"]["recent"].setdefault(f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)
            
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
        chars["characters"][wolf]["memory"]["recent"].setdefault(f"round_{current_round}_night_wolfvote",[]).append(mem_snippet)

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
        char["memory"]["recent"].setdefault(f"round_{current_round}_morning_announcement",[]).append(mem_snippet)
        
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
    SYSTEM_PROMPT_CHALLENGE = """
        You are simulating a character in a social deduction game.

        You are the Knight. You may challenge ONE player in the entire game.

        Rules:
        - Only challenge if you believe it significantly improves your team's chance of winning.
        - If you challenge:
        - If target is a werewolf: they die
        - Otherwise: BOTH you and target die
        - This action immediately ends the day (no vote)

        Use ONLY provided information.
        Do NOT invent facts.

        Output STRICT JSON:
        {
        "internal_reasoning": "(max 120 words)",
        "answer": "(target_name OR no)"
        }
    """

    ability = chars["characters"][speaker]["game_status"]["ability"]

    if ability.get("challenge_chance", 0) <= 0:
        return False

    challenge_prompt = {
        "character_information": view,
        "question": "Do you want to challenge a player? If yes, answer the target's name. If no, answer 'no'.",
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
        raw_content = response.choices[0].message.content
        content = raw_content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)

        raw_answer = data.get("answer")
        internal_reasoning = data.get("internal_reasoning", "")[:1200]
        answer = normalize_choice(raw_answer, valid_targets + ["no"])

        parsed = {
            "raw_answer": raw_answer,
            "normalized_answer": answer,
            "internal_reasoning": internal_reasoning
        }
        log_llm_interaction(speaker, "knight_challenge", "", raw_content, parsed)
    
    except Exception as e:
        log_error("knight_challenge_decision", e)
        answer = "no"
        internal_reasoning = ""

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
                "internal_reasoning": internal_reasoning if answer else ""
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
    SYSTEM_PROMPT_REVEAL = """
        You are simulating a character in a social deduction game.

        You are a Werewolf. You may reveal yourself publicly.

        Rules:
        - If you reveal:
        - You die immediately
        - The day ends (no vote)
        - ONLY reveal if it benefits the werewolf team strategically

        Constraints:
        - Use ONLY provided information
        - Do NOT invent facts

        Output STRICT JSON:
        {
        "internal_reasoning": "(max 120 words)",
        "answer": "(yes OR no)"
        }
    """
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

        raw_content = response.choices[0].message.content
        content = raw_content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)

        raw_answer = data.get("answer", "no")
        internal_reasoning = data.get("internal_reasoning", "")[:1200]
        answer = normalize_choice(raw_answer, ["yes", "no"])

        parsed = {
            "raw_answer": raw_answer,
            "normalized_answer": answer,
            "internal_reasoning": internal_reasoning
        }
        log_llm_interaction(speaker, "wolf_reveal", "", raw_content, parsed)

    except Exception as e:
        log_error("wolf_reveal", e)
        answer = "no"

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
    SYSTEM_PROMPT_SPEECH = """
        You are simulating a character in a structured social deduction game.
        This is daytime public discussion. Players are deciding who to eliminate today.
        Some players may lie, manipulate, hide information, or test reactions.
        
        Now it's your turn to speak. All living players can hear your speech clearly.
        Your speech may influence suspicion, trust, alliances, and votes.
        
        Rules:
        - You MUST use ONLY the information provided in the input.
        - You MUST NOT invent, assume, or hallucinate any information not presented.
        - You MUST stay consistent with your personality, goals and knowledge.
        - You MAY reference your memory as provided.
        - You MAY suspect, accuse, defend, question, pressure, mislead, calm others, or stay cautious strategically.
        - You do NOT know hidden roles unless explicitly supported by your information.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; MAXIMUM 120 words.
        - Provide public speech to all players; MAXIMUM 120 words.
        - Be natural, strategic, concise, and consistent with character identity.

        Return STRICT JSON in this format:
        {
        "internal_reasoning": "",
        "speech": ""
        }
    """
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
            payload = {
                "character_information": view,
                "introduction": (
                    f"This is the day phase public discussion. "
                    f"This is discussion round {discuss_round} of 2 before voting."
                ),
                "reminder": (
                    "Your objective is to help your team win the game. "
                    "Consider carefully what you say, as it may determine who (including you) will be eliminated today."
                ),
                "audience": valid_targets,
            }
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_SPEECH},
                        {"role": "user", "content": json.dumps(payload)}
                    ]
                )

                raw_content = response.choices[0].message.content
                content = raw_content.replace("```json", "").replace("```", "").strip()
                data = json.loads(content)

                internal_reasoning = data.get("internal_reasoning", "")[:1200]
                speech = data.get("speech", "")[:1200]

                parsed = {
                    "speech": speech,
                    "internal_reasoning": internal_reasoning
                }
                log_llm_interaction(speaker, "public_discussion", "", raw_content, parsed)

            except Exception as e:
                internal_reasoning, speech = "", "..."
                log_error("public_speech", e)

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
            chars["characters"][speaker]["memory"]["recent"].setdefault(f"round_{current_round}_day_discuss_round_{discuss_round}", []).append(mem_snippet)

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
                chars["characters"][listener]["memory"]["recent"].setdefault(f"round_{current_round}_day_discuss_round_{discuss_round}", []).append(mem_snippet)

                RECENT_MEMORY_COUNTER[listener] = RECENT_MEMORY_COUNTER.get(listener,0)+1
                trim_recent_memory(chars["characters"][listener], RECENT_MEMORY_COUNTER[listener])

            save_json(CHARACTERS_FILE, chars)

    # =====================================
    # VOTING PHASE
    # =====================================
    SYSTEM_PROMPT_VOTE = """
        You are simulating a character in a structured social deduction game.
        It is now the daytime public voting time.
        You will choose one living player to vote for elimination today.

        Your vote may determine who is eliminated.
        Consider all available information presented: speeches, behavior, contradictions, alliances, pressure, risks, and your role objective.

        Rules:
        - You MUST use ONLY the information provided in the input.
        - You MUST NOT invent, assume, or hallucinate any information not provided.
        - You MUST stay consistent with your personality, goals, and knowledge.
        - You MUST choose ONLY from the valid options provided.
        - You may vote strategically, defensively, aggressively, deceptively, or cooperatively depending on your incentives.

        Output requirements:
        - Provide a brief internal reasoning summary of the character; MAXIMUM 120 words.
        - Provide exactly one vote target from valid options.
        - Be precise and decisive.

        Return STRICT JSON in this format:
        {
        "internal_reasoning": "",
        "vote": ""
        }
    """
    votes = {}
    for voter in speak_order:
        if chars["characters"][voter]["game_status"]["is_dead"]:
            continue

        view = build_llm_view(chars, voter)
        valid_targets = get_valid_targets(chars, exclude=[])
        valid_options = valid_targets + ["abstain"]

        payload = {
            "character_information": view,
            "introduction": (
                "The public discussion has ended. "
                "Now all living players vote to eliminate one player."
            ),
            "reminder": (
                "Your objective is to help your team win the game. "
                "Consider your vote carefully, as it may determine who (including you) will be eliminated today."
            ),
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

            raw_content = response.choices[0].message.content
            content = raw_content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

            internal_reasoning = data.get("internal_reasoning", "")[:1200]
            raw_answer = str(data.get("vote", "")).strip()
            vote = normalize_choice(raw_answer, valid_options)

            parsed = {
                "raw_answer": raw_answer,
                "normalized_answer": vote,
                "internal_reasoning": internal_reasoning
            }
            log_llm_interaction(voter, "public_vote", "", raw_content, parsed)

        except Exception as e:
            internal_reasoning = ""
            vote = "abstain"
            log_error("public_vote", e)
        
        # ---------------------------------
        # SELF MEMORY (vote cast)
        # ---------------------------------
        mem_snippet = {
            "memory_owner": voter,
            "source_type": "self",
            "phase_step": "day_vote",
            "content": {
                "performer": voter,
                "action": f"voted to eliminate {vote}" if vote and vote != "abstain" else "abstain",
                "internal_reasoning": internal_reasoning if vote else ""
            },
            "metadata": {
                "impact": 100,
                "confidence": 100
            }
        }
        chars["characters"][voter]["memory"]["recent"].setdefault(f"round_{current_round}_day_vote", []).append(mem_snippet)

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
                    "action": f"voted to eliminate {vote}" if vote and vote != "abstain" else "abstain",
                },
                "metadata": {
                    "impact": 90,
                    "confidence": 100
                }
            }
            chars["characters"][observer]["memory"]["recent"].setdefault(f"round_{current_round}_day_vote", []).append(mem_snippet)

            RECENT_MEMORY_COUNTER[observer] = RECENT_MEMORY_COUNTER.get(observer,0)+1
            trim_recent_memory(chars["characters"][observer], RECENT_MEMORY_COUNTER[observer])

        save_json(CHARACTERS_FILE, chars)

        # COUNT THE VOTE:
        if vote not in valid_options:
            vote = "abstain"
        votes[vote] = votes.get(vote, 0) + 1

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
        char["memory"]["recent"].setdefault(f"round_{current_round}_day_vote", []).append(mem_snippet)

        RECENT_MEMORY_COUNTER[name] = RECENT_MEMORY_COUNTER.get(name,0)+1
        trim_recent_memory(chars["characters"][name], RECENT_MEMORY_COUNTER[name])

        if eliminated:
            char["knowledge"]["characters"][eliminated]["game_status"]["is_dead"] = {"value": True, "confidence": 100}

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

    # ---- game setup ----
    initialize_game_state()
    CHARACTER_NAMES = ["AA", "CO", "DO", "FO", "GA", "LO", "MA", "NO", "PA", "SA", "TO", "VA", "WA", "YA"]

    # characters initialization problems here. currently fixed character profile. will resolve later.
    # ---- user option ----
    while True:
        choice = input("If to use randomized trait setup for characters? (yes or no): ").strip().lower()
        if choice == "yes":
            use_random_traits = True
            break
        elif choice == "no":
            use_random_traits = False
            break
        else:
            print("Invalid choice.")
    initialize_characters(CHARACTER_NAMES)

    # ---- continue setup ----
    initialize_characters_scene_world()

    public_event("Initialization finished.")

    while True:
        game = load_json(GAME_ROUNDS_FILE, {"current_round": 0})
        game["current_round"] += 1
        current_round = game["current_round"]
        save_json(GAME_ROUNDS_FILE, game)

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
