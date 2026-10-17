"""Run the configurable order assistant or a local data check."""

import argparse
import getpass
from dataclasses import replace

from config import load_config
from tools import get_order_status


def main():
    parser = argparse.ArgumentParser(description="Factory order assistant")
    parser.add_argument("--local", action="store_true", help="Query ORD-120 without an API call")
    parser.add_argument("--api", action="store_true", help="Serve local HTTP on 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--init-db", action="store_true", help="Create the project session table and exit")
    args = parser.parse_args()
    if args.local:
        print(get_order_status("ORD-120"))
        return

    from storage import SQLiteStore
    from service import ChatService
    try:
        store = SQLiteStore()
        store.setup()
    except Exception:
        print("Could not initialize SQLite. Check SQLITE_PATH and folder write permission.")
        return
    if args.init_db:
        print(f"Project session table is ready: {store.path}")
        return

    while True:
        provider = input("Choose provider (DeepSeek / OpenAI, or exit): ").strip().lower()
        if provider in {"exit", "quit"}:
            return
        if provider in {"deepseek", "openai"}:
            break
        print("Please enter DeepSeek or OpenAI.")

    try:
        config = load_config(provider)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return
    print(f"Provider: {config.provider} | Model: {config.model}")
    # Always use the key entered for this session, even if .env has a saved key.
    while True:
        key = getpass.getpass(f"{config.provider} API key (hidden input): ").strip()
        if key:
            break
        print("API key cannot be empty. Try again, or press Ctrl+C to exit.")
    config = replace(config, api_key=key)
    service = ChatService(store, config)
    if args.api:
        import uvicorn
        from api import create_app
        uvicorn.run(create_app(service), host="127.0.0.1", port=args.port)
        return
    session_id = service.create_session()["id"]
    print(f"Session: {session_id}")
    print("Commands: /new, /sessions, /use SESSION_ID, /history, exit")
    print(f"Requests use your {config.provider} balance. Completed turns are stored in local SQLite.")
    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if question == "/new":
            session_id = service.create_session()["id"]
            print(f"Session: {session_id}")
            continue
        if not question:
            continue
        try:
            if question == "/sessions":
                for session in service.list_sessions():
                    print(session)
            elif question.startswith("/use "):
                requested = question[5:].strip()
                service.get_history(requested)
                session_id = requested
                print(f"Session: {session_id}")
            elif question == "/history":
                for message in service.get_history(session_id):
                    print(message)
            else:
                print(f"Assistant: {service.send_message(session_id, question)['answer']}")
        except KeyError:
            print("Session not found.")
        except Exception:
            print("Request failed. Check database/model settings; the completed history was not changed.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
