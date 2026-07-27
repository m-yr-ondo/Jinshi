"""
AI Chat Cog for Logiq
AI-powered chatbot and content moderation
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, List
import logging
import aiohttp

from utils.embeds import EmbedFactory, EmbedColor
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class AIChat(commands.Cog):
    """AI chat and moderation cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('ai_chat', {})
        self.api_key = config.get('api_keys', {}).get('openai', '')
        self.provider = self.module_config.get('provider', 'openai')
        self.model = self.module_config.get('model', 'gpt-4')
        self.conversation_history: Dict[int, List[Dict]] = {}

    async def call_openai(self, messages: List[Dict], max_tokens: int = 500) -> Optional[str]:
        """Call OpenAI API"""
        if not self.api_key:
            return "OpenAI API key not configured"

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self.module_config.get('temperature', 0.7)
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {error_text}")
                        return "Error calling AI service"
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}", exc_info=True)
            return "Error calling AI service"

    async def moderate_content(self, text: str) -> Dict:
        """Moderate content using OpenAI moderation API"""
        if not self.api_key:
            return {"flagged": False}

        url = "https://api.openai.com/v1/moderations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {"input": text}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['results'][0]
                    return {"flagged": False}
        except Exception as e:
            logger.error(f"Error moderating content: {e}", exc_info=True)
            return {"flagged": False}

    @app_commands.command(name="ask", description="Ask AI a question")
    @app_commands.describe(question="Your question for the AI")
    async def ask(self, interaction: discord.Interaction, question: str):
        """Ask AI a question"""
        if not self.module_config.get('enabled', True):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Module Disabled", "AI chat is currently disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Get or create conversation history
        user_id = interaction.user.id
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []

        # Add user message
        self.conversation_history[user_id].append({
            "role": "user",
            "content": question
        })

        # Limit history
        max_history = 10
        if len(self.conversation_history[user_id]) > max_history:
            self.conversation_history[user_id] = self.conversation_history[user_id][-max_history:]

        # Add system message
        messages = [
            {
                "role": "system",
                "content": "You are Logiq, a helpful AI assistant for Discord communities. "
                          "Be concise, friendly, and helpful."
            }
        ] + self.conversation_history[user_id]

        # Get AI response
        response = await self.call_openai(messages, max_tokens=500)

        if response:
            # Add to history
            self.conversation_history[user_id].append({
                "role": "assistant",
                "content": response
            })

            embed = EmbedFactory.ai_response(response, self.model)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                embed=EmbedFactory.error("Error", "Failed to get AI response"),
                ephemeral=True
            )

    @app_commands.command(name="clear-conversation", description="Clear your AI conversation history")
    async def clear_conversation(self, interaction: discord.Interaction):
        """Clear conversation history"""
        user_id = interaction.user.id
        if user_id in self.conversation_history:
            self.conversation_history[user_id] = []

        await interaction.response.send_message(
            embed=EmbedFactory.success("Conversation Cleared", "Your AI conversation history has been reset"),
            ephemeral=True
        )

    @app_commands.command(name="summarize", description="Summarize recent messages in channel")
    @app_commands.describe(count="Number of messages to summarize (max 100)")
    async def summarize(self, interaction: discord.Interaction, count: int = 50):
        """Summarize recent messages"""
        if not self.module_config.get('enabled', True):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Module Disabled", "AI chat is currently disabled"),
                ephemeral=True
            )
            return

        if count < 1 or count > 100:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Count", "Count must be between 1 and 100"),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # Fetch messages
            messages = []
            async for message in interaction.channel.history(limit=count):
                if not message.author.bot and message.content:
                    messages.append(f"{message.author.name}: {message.content}")

            if not messages:
                await interaction.followup.send(
                    embed=EmbedFactory.info("No Messages", "No messages to summarize"),
                    ephemeral=True
                )
                return

            # Reverse to chronological order
            messages.reverse()
            conversation_text = "\n".join(messages)

            # Ask AI to summarize
            prompt = f"Summarize this Discord conversation concisely:\n\n{conversation_text}"
            response = await self.call_openai([
                {"role": "system", "content": "You are a helpful assistant that summarizes conversations."},
                {"role": "user", "content": prompt}
            ], max_tokens=300)

            if response:
                embed = EmbedFactory.create(
                    title="📝 Conversation Summary",
                    description=response,
                    color=EmbedColor.AI
                )
                embed.set_footer(text=f"Summarized {len(messages)} messages")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    embed=EmbedFactory.error("Error", "Failed to generate summary"),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error summarizing messages: {e}", exc_info=True)
            await interaction.followup.send(
                embed=EmbedFactory.error("Error", "An error occurred while summarizing"),
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Check messages for toxicity"""
        if not self.module_config.get('enabled', True):
            return

        if message.author.bot or not message.guild:
            return

        # Check if auto-moderation is enabled
        module_config = self.config.get('modules', {}).get('moderation', {})
        if not module_config.get('auto_mod', {}).get('toxicity_filter', False):
            return

        # Moderate content
        moderation_result = await self.moderate_content(message.content)

        if moderation_result.get('flagged', False):
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Your message was removed for violating community guidelines.",
                    delete_after=10
                )
                logger.info(f"Auto-moderated message from {message.author} in {message.guild}")
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(AIChat(bot, bot.db, bot.config))
