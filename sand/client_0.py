import asyncio



def main():
    print("Connected. Type your message and press Enter. Ctrl+C to quit.\n")

    while True:
        print("waiting for user input...")
        user_input = input("You: ")
        if not user_input.strip():
            break
        print("user input received!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
