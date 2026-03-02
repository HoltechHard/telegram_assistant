from llm_client import query_llm

def main():
    print("=== KIMI Local Test ===")
    print("Type your question (or 'exit'):\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() == "exit":
            break

        try:
            response = query_llm(user_input)
            print("\nKIMI:")
            print(response)
            print("\n" + "-" * 40 + "\n")

        except Exception as e:
            print("Error:", str(e))


if __name__ == "__main__":
    main()