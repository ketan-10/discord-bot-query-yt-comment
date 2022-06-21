import discord
from handlers import handle_add_channel, handle_search
import os
import traceback

from dotenv import load_dotenv
load_dotenv()

client = discord.Client()

print("Hello world")

@client.event
async def on_ready():
    print(f"{client.user} has connected to Discord!")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    print(f"got a message {message.author}: {message.content}")

    if message.content == "hello":
        print("Hello!!!")
        await message.reply("Hello!!")
    words = message.content.split(' ')
    # check for add-channel command.
    if len(words) == 3 and message.content.startswith('add-channel'):
        channelName = words[1]
        channelId = words[2]
        await message.add_reaction("🔃")
        try:
            response = await handle_add_channel(channelId, channelName)

            if(response['success']):
                await message.add_reaction("✅")
            else:
                print(response)
                await message.add_reaction("❌")
            await message.reply(response["message"])
        except Exception:
            print(traceback.format_exc())
            await message.add_reaction("❌")
    
    if len(words) > 2 and words[1] == "says":
        channel = words[0]
        query = " ".join(words[2:]) 
        try:
            response = await handle_search(query, channel)
            if(response['success']):
                await message.reply(response["message"])
            else:
                # await message.reply("Probably not!!")
                await message.reply(response["message"])
        except Exception:
            print(traceback.format_exc())
            await message.add_reaction("❌")

client.run(os.environ['DISCORD_TOKEN'])