import asyncio

import websockets


SERVER_URL = "ws://localhost:8000/chat"


async def main():
    print(f"Connecting to {SERVER_URL}...")
    async with websockets.connect(SERVER_URL) as ws:
        print("Connected. Type your message and press Enter. Ctrl+C to quit.\n")
        loop = asyncio.get_event_loop()

        while True:
            user_input = await loop.run_in_executor(None, input, "You: ")
            if not user_input.strip():
                continue

            await ws.send(user_input)

            print("Assistant: ", end="", flush=True)
            async for message in ws:
                if message == "[END]":
                    print()
                    break
                print(message, end="", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye.")
