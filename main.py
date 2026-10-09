"""Run the configurable order assistant or a local data check."""

import argparse
import getpass
from dataclasses import replace

from llm import ask_llm
from llm_config import load_config
from tools import get_order_status


def main():
    parser = argparse.ArgumentParser(description="Factory order assistant")
    parser.add_argument("--local", action="store_true", help="Query ORD-120 without an API call")
    args = parser.parse_args()
    if args.local:
        print(get_order_status("ORD-120"))
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
    print("Factory order assistant. Each question starts a new conversation.")
    print(f"Type exit to quit. API requests use your {config.provider} balance.")
    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        try:
            print(f"Assistant: {ask_llm(question, config)}")
        except RuntimeError as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
