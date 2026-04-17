import asyncio

async def super_main():
        task1 = asyncio.create_task(main())
        task2 = asyncio.create_task(dots())

        await task1
        await task2


async def dots():
    while True:
        print(".", end="", flush=True)
        await asyncio.sleep(1)

async def main():
    print("Connected. Type your message and press Enter. Ctrl+C to quit.\n")
    loop = asyncio.get_event_loop()

    while True:
        print("waiting for user input...")
        user_input = await loop.run_in_executor(None, input, "You: ") 
        if not user_input.strip():
            continue
        print("user input received!")

if __name__ == "__main__":
    try:
        asyncio.run(super_main())
    except KeyboardInterrupt:
        print("\nBye.")
