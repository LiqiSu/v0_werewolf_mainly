import os
import json
from datetime import datetime
from groq import Groq

# =========================
# CONFIG
# =========================
API_KEY = "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"  # <-- PUT YOUR KEY HERE
MODEL = "llama-3.3-70b-versatile"

DATA_DIR = "data"
WORLD_BIBLE_FILE = os.path.join(DATA_DIR, "world_bible.json")
STYLE_GUIDE_FILE = os.path.join(DATA_DIR, "style_guide.txt")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.json")
SCENE_STATE_FILE = os.path.join(DATA_DIR, "scene_state.json")

SHORT_MEMORY_FILE = os.path.join(DATA_DIR, "memory_short.json")
MEDIUM_MEMORY_FILE = os.path.join(DATA_DIR, "memory_medium.json")
LONG_ARCHIVE_FILE = os.path.join(DATA_DIR, "memory_long_archive.json")
LONG_SUMMARY_FILE = os.path.join(DATA_DIR, "long_term_summary.txt")

EVENT_LOG_FILE = os.path.join(DATA_DIR, "event_log.txt")
CHAPTER_LOG_FILE = os.path.join(DATA_DIR, "chapters.txt")

os.makedirs(DATA_DIR, exist_ok=True)

client = Groq(api_key=API_KEY)

# =========================
# FILE HELPERS
# =========================
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default

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
# INITIALIZE FILES IF MISSING
# =========================
def init_files():
    # Create empty files if missing, but do NOT fill defaults
    if not os.path.exists(WORLD_BIBLE_FILE):
        save_json(WORLD_BIBLE_FILE, {
            "setting": "",
            "rules": "",
            "factions": [],
            "important_places": [],
            "important_events": [],
            "tone": ""
        })

    if not os.path.exists(STYLE_GUIDE_FILE):
        save_text(STYLE_GUIDE_FILE, "")

    if not os.path.exists(CHARACTERS_FILE):
        save_json(CHARACTERS_FILE, {"characters": {}})

    if not os.path.exists(SCENE_STATE_FILE):
        save_json(SCENE_STATE_FILE, {
            "location": "",
            "characters_present": [],
            "tone": "",
            "objective": "",
            "constraints": ""
        })

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
def build_prompt(user_instruction):
    world = load_json(WORLD_BIBLE_FILE, {})
    style = load_text(STYLE_GUIDE_FILE, "")
    chars = load_json(CHARACTERS_FILE, {})
    scene = load_json(SCENE_STATE_FILE, {})
    short_mem = load_json(SHORT_MEMORY_FILE, {"summaries": []})
    medium_mem = load_json(MEDIUM_MEMORY_FILE, {"summaries": []})
    long_summary = load_text(LONG_SUMMARY_FILE, "")

    short_block = "\n".join(f"- {s}" for s in short_mem["summaries"])
    medium_block = "\n".join(f"- {s}" for s in medium_mem["summaries"][-15:])

    system_instructions = (
        "你是一名长篇小说叙事作者。\n"
        "使用第三人称视角进行叙事（“他 / 她 / 他们”）。\n"
        "保持世界观、角色状态与事件的连续性。\n"
        "文风需符合简体中文的自然叙事习惯。\n"
        "不要在每段输出中重复总结剧情，只需自然延续故事。\n"
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
        "# 写作指令\n"
        f"{user_instruction}\n\n"
        "请继续以第三人称视角推进故事，自然衔接前文，保持叙事风格一致。\n"
    )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": full_prompt}
    ]
    return messages

# =========================
# GROQ CALL: STORY GENERATION
# =========================
def generate_story(user_instruction):
    messages = build_prompt(user_instruction)
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

# =========================
# GROQ CALL: CHARACTER UPDATES
# =========================
def update_characters_from_output(story_output):
    chars = load_json(CHARACTERS_FILE, {"characters": {}})

    prompt = (
        "You are an information extraction assistant.\n"
        "Given a story segment and the current character sheets, "
        "update only what has clearly changed.\n"
        "Return STRICT JSON with this schema:\n"
        "{\n"
        '  "characters": {\n'
        '    "Name": {\n'
        '      "physical_state": "string (optional)",\n'
        '      "mental_state": "string (optional)",\n'
        '      "location": "string (optional)",\n'
        '      "activity": "string (optional)",\n'
        '      "clothing": "string (optional)",\n'
        '      "recent_events": ["list of short strings (optional)"]\n'
        "    }\n"
        "  }\n"
        "}\n"
        "Only include fields that actually changed or are newly implied.\n"
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
        return  # fail silently

    if "characters" not in updates:
        return

    for name, changes in updates["characters"].items():
        if name not in chars["characters"]:
            chars["characters"][name] = {
                "appearance": "",
                "clothing": "",
                "personality": "",
                "goals": "",
                "physical_state": "",
                "mental_state": "",
                "location": "",
                "activity": "",
                "recent_events": []
            }
        char = chars["characters"][name]
        for field, value in changes.items():
            if field == "recent_events":
                if "recent_events" not in char or not isinstance(char["recent_events"], list):
                    char["recent_events"] = []
                for ev in value:
                    if ev not in char["recent_events"]:
                        char["recent_events"].append(ev)
            else:
                if isinstance(value, str) and value.strip():
                    char[field] = value.strip()

    save_json(CHARACTERS_FILE, chars)

# =========================
# GROQ CALL: SCENE UPDATES
# =========================
def update_scene_from_output(story_output):
    scene = load_json(SCENE_STATE_FILE, {
        "location": "",
        "characters_present": [],
        "tone": "",
        "objective": "",
        "constraints": ""
    })

    prompt = (
        "You are an information extraction assistant.\n"
        "Given a story segment and the current scene state, update only what has clearly changed.\n"
        "Return STRICT JSON with this schema:\n"
        "{\n"
        "  \"location\": \"string (optional)\",\n"
        "  \"characters_present\": [\"list of names (optional)\"],\n"
        "  \"tone\": \"string (optional)\",\n"
        "  \"objective\": \"string (optional)\",\n"
        "  \"constraints\": \"string (optional)\"\n"
        "}\n"
        "Only include fields that actually changed or are newly implied.\n"
        "If nothing changed, return {}.\n"
    )

    payload = {
        "story_segment": story_output,
        "current_scene": scene
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

    if not isinstance(updates, dict):
        return

    for field, value in updates.items():
        if field == "characters_present":
            if isinstance(value, list):
                scene["characters_present"] = value
        else:
            if isinstance(value, str) and value.strip():
                scene[field] = value.strip()

    save_json(SCENE_STATE_FILE, scene)

# =========================
# GROQ CALL: WORLD UPDATES
# =========================
def update_world_from_output(story_output):
    world = load_json(WORLD_BIBLE_FILE, {
        "setting": "",
        "rules": "",
        "factions": [],
        "important_places": [],
        "important_events": [],
        "tone": ""
    })

    prompt = (
        "You are an information extraction assistant.\n"
        "Given a story segment and the current world bible, extract only NEW important world information.\n"
        "Return STRICT JSON with this schema:\n"
        "{\n"
        "  \\\"factions\\\": [\\\"optional list of new or updated faction names\\\"],\n"
        "  \\\"important_places\\\": [\\\"optional list of new or updated place names\\\"],\n"
        "  \\\"important_events\\\": [\\\"optional list of short descriptions of major events\\\"]\n"
        "}\n"
        "If there is nothing clearly new or important, return {}.\n"
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

    content = response.choices[0].message["content"]
    try:
        updates = json.loads(content)
    except json.JSONDecodeError:
        return

    if not isinstance(updates, dict):
        return

    for field in ["factions", "important_places", "important_events"]:
        if field in updates and isinstance(updates[field], list):
            if field not in world or not isinstance(world[field], list):
                world[field] = []
            for item in updates[field]:
                if item not in world[field]:
                    world[field].append(item)

    save_json(WORLD_BIBLE_FILE, world)

# =========================
# MAIN LOOP
# =========================
def main():
    init_files()
    memory_manager = MemoryManager()

    print("Story engine ready.")
    print("Type a prompt like: 'Begin the story.' or 'Continue the next scene.'")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("You (instruction to story engine): ")
        if user_input.lower().strip() == "exit":
            break

        story_output = generate_story(user_input)

        print("\n--- Story Output ---\n")
        print(story_output)
        print("\n--------------------\n")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_text(CHAPTER_LOG_FILE, f"[{timestamp}] CHAPTER:\n{story_output}\n")

        # Auto-update world, characters, scene
        update_characters_from_output(story_output)
        update_scene_from_output(story_output)
        update_world_from_output(story_output)

        # Summarize and update memory
        summary = summarize_output_for_memory(story_output)
        memory_manager.add_event_summary(summary)

if __name__ == "__main__":
    main()
