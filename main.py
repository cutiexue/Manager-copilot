"""Run the configurable order assistant or a local data check."""

import argparse
import getpass
from dataclasses import replace

from config import load_config
from tools import get_order_status


def preview_session(service, session_id):
    """Show a short excerpt without asking the model to summarize."""
    history = service.get_history(session_id)
    print("Conversation opened. Messages are saved automatically.")
    if not history:
        print("No messages yet.")
    for role, label in (("human", "Last question"), ("ai", "Last answer")):
        item = next((m for m in reversed(history) if m["role"] == role), None)
        if item:
            text = " ".join(str(item["content"]).split())
            print(f"{label}: {text[:180]}{'...' if len(text) > 180 else ''}")


def choose_session(service, current=None):
    """Return a selected session, or keep the current one on cancellation."""
    sessions = service.list_sessions()
    if not sessions:
        print("No saved conversations.")
        return current
    for index, session in enumerate(sessions, 1):
        print(f"{index}. {session['title']} | {session['updated_at']}")
    while True:
        choice = input("Conversation number, /1 latest, /3 new, /4 briefing, /0 exit (Enter to cancel): ").strip()
        if not choice:
            return current
        if choice.lower() in {'/0', 'exit', 'quit'}:
            raise SystemExit(0)
        if choice in {'/3', '/new'}:
            return service.create_session()['id']
        if choice in {'/1', '/latest', '/4', '/briefing'}:
            latest = next((s for s in sessions if s.get('has_messages', True)), None)
            selected = (current if choice in {'/4', '/briefing'} else None)
            selected = selected or (latest['id'] if latest else service.create_session()['id'])
            if choice in {'/4', '/briefing'}:
                print(service.morning_briefing(selected)['answer'])
            else:
                preview_session(service, selected)
            return selected
        if choice in {'/2', '/sessions', '/session'}:
            for index, session in enumerate(sessions, 1):
                print(f"{index}. {session['title']} | {session['updated_at']}")
            continue
        if choice.isdecimal() and 1 <= int(choice) <= len(sessions):
            selected = sessions[int(choice) - 1]['id']
            preview_session(service, selected)
            return selected
        print("Use a listed conversation number, /3 to create, /0 to exit, or Enter to cancel.")


def session_menu(service, current=None):
    """Numbered actions are only interpreted inside this menu."""
    while True:
        sessions = service.list_sessions()
        latest = next((s for s in sessions if s.get('has_messages', True)), None)
        print("\n1. Continue latest conversation" + (f": {latest['title']}" if latest else " (none)"))
        print("2. Open conversation history\n3. Start new conversation\n4. View morning briefing\n0. Exit")
        choice = input("Choose an action (Enter = 1): ").strip() or '1'
        choice = {'/1': '1', '/2': '2', '/3': '3', '/4': '4', '/0': '0',
                  '/latest': '1', '/sessions': '2', '/new': '3', '/briefing': '4',
                  'exit': '0', 'quit': '0'}.get(choice, choice)
        if choice == '0':
            return None
        if choice == '1':
            selected = latest['id'] if latest else service.create_session()['id']
            preview_session(service, selected)
            return selected
        if choice == '2':
            selected = choose_session(service, current)
            if selected:
                return selected
        elif choice == '3':
            return service.create_session()['id']
        elif choice == '4':
            selected = current or (latest['id'] if latest else service.create_session('Morning briefing')['id'])
            print(service.morning_briefing(selected)['answer'])
            return selected
        elif choice != '2':
            print("Please choose 0, 1, 2, 3 or 4.")


def run_chat(service):
    session_id = session_menu(service)
    print("Shortcuts: /1 latest, /2 history list, /3 new, /4 briefing, /0 exit. Type /menu for the menu.")
    aliases = {'/1': '/latest', '/2': '/sessions', '/3': '/new', '/4': '/briefing', '/0': 'exit'}
    while session_id:
        question = input("You: ").strip()
        question = aliases.get(question, question)
        if question.lower() in {'exit', 'quit'}:
            return
        if not question:
            continue
        try:
            if question == '/menu':
                session_id = session_menu(service, session_id)
            elif question == '/latest':
                latest = next((s for s in service.list_sessions() if s.get('has_messages', True)), None)
                if latest:
                    preview_session(service, latest['id'])
                    session_id = latest['id']
                else:
                    print("No saved messages yet. Continue this conversation or use /3 to start another.")
            elif question == '/new':
                session_id = service.create_session()['id']
                print("New conversation. Previous conversations remain saved.")
            elif question in {'/sessions', '/session'}:
                session_id = choose_session(service, session_id)
            elif question == '/history':
                for item in service.get_history(session_id):
                    print(f"{item['role']}: {item['content']}")
            elif question == '/briefing':
                print(service.morning_briefing(session_id)['answer'])
            elif question.startswith('/use '):
                from uuid import UUID
                candidate = question[5:].strip()
                try:
                    UUID(candidate)
                except ValueError:
                    print("Use /sessions to select a conversation by number.")
                    continue
                preview_session(service, candidate)
                session_id = candidate
            elif question.startswith('/') or question.lower().startswith('use '):
                print("Unknown command. Type /menu or /sessions; manual switching uses /use SESSION_ID.")
            else:
                print(f"Assistant: {service.send_message(session_id, question)['answer']}")
        except KeyError:
            print("Session not found. Use /sessions to select a saved conversation.")
        except Exception:
            print("Request failed. Completed messages remain saved; check database/model settings.")


def main():
    parser = argparse.ArgumentParser(description="Factory order assistant")
    parser.add_argument("--local", action="store_true", help="Query ORD-120 without an API call")
    parser.add_argument("--api", action="store_true", help="Serve local HTTP on 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--provider", choices=("deepseek", "openai"),
                        help="Override the provider saved in .env")
    parser.add_argument("--init-db", action="store_true", help="Create the project session table and exit")
    args = parser.parse_args()
    if args.local:
        print(get_order_status("ORD-120"))
        return

    from storage import MySQLStore
    from service import ChatService
    try:
        try:
            store = MySQLStore()
        except ValueError:
            store = MySQLStore(password=getpass.getpass("MySQL project password (hidden): "))
        store.setup()
    except Exception:
        print("Could not initialize MySQL. Check project credentials, service and CREATE permission.")
        return
    if args.init_db:
        print("Project session table is ready.")
        return

    try:
        config = load_config(args.provider)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return
    print(f"Provider: {config.provider} | Model: {config.model}")
    # 已保存密钥时直接使用；缺失时才隐藏输入。
    while not config.api_key:
        key = getpass.getpass(f"{config.provider} API key (hidden input): ").strip()
        if key:
            config = replace(config, api_key=key)
        else:
            print("API key cannot be empty. Try again, or press Ctrl+C to exit.")
    service = ChatService(store, config)
    if args.api:
        import uvicorn
        from api import create_app
        uvicorn.run(create_app(service), host="127.0.0.1", port=args.port)
        return
    run_chat(service)



if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
