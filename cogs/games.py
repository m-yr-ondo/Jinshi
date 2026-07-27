"""
Games Cog for Logiq
Button-based interactive mini-games for users
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging
import random

from utils.embeds import EmbedFactory, EmbedColor
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class DiceGameView(discord.ui.View):
    """Button-based dice game"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🎲 Roll Dice", style=discord.ButtonStyle.primary, custom_id="dice_roll")
    async def roll_dice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Roll a dice"""
        result = random.randint(1, 6)

        embed = EmbedFactory.create(
            title="🎲 Dice Roll",
            description=f"{interaction.user.mention} rolled:\n\n# {result}",
            color=EmbedColor.INFO
        )

        await interaction.response.send_message(embed=embed)


class CoinFlipView(discord.ui.View):
    """Button-based coinflip game"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🪙 Heads", style=discord.ButtonStyle.success, custom_id="coin_heads")
    async def flip_heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bet on heads"""
        await self._flip_coin(interaction, "heads")

    @discord.ui.button(label="🪙 Tails", style=discord.ButtonStyle.danger, custom_id="coin_tails")
    async def flip_tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bet on tails"""
        await self._flip_coin(interaction, "tails")

    async def _flip_coin(self, interaction: discord.Interaction, choice: str):
        """Flip coin logic"""
        result = random.choice(["heads", "tails"])
        won = result == choice

        if won:
            embed = EmbedFactory.success(
                "🎉 You Won!",
                f"{interaction.user.mention} bet on **{choice}** and the coin landed on **{result}**!"
            )
        else:
            embed = EmbedFactory.error(
                "You Lost!",
                f"{interaction.user.mention} bet on **{choice}** but the coin landed on **{result}**!"
            )

        await interaction.response.send_message(embed=embed)


class TriviaView(discord.ui.View):
    """Button-based trivia game"""

    def __init__(self, cog, question_data):
        super().__init__(timeout=30)
        self.cog = cog
        self.question_data = question_data
        self.answered = False

        # Create buttons for each option
        for i, option in enumerate(question_data['options']):
            button = discord.ui.Button(
                label=option,
                style=discord.ButtonStyle.primary,
                custom_id=f"trivia_{i}"
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, option_index):
        async def callback(interaction: discord.Interaction):
            if self.answered:
                await interaction.response.send_message("This trivia has been answered!", ephemeral=True)
                return

            self.answered = True
            correct = option_index == self.question_data['answer']

            if correct:
                await self.cog.db.add_balance(interaction.user.id, interaction.guild.id, 50)
                embed = EmbedFactory.success(
                    "Correct! 🎉",
                    f"{interaction.user.mention} got it right!\nYou earned **💎 50**!"
                )
            else:
                correct_answer = self.question_data['options'][self.question_data['answer']]
                embed = EmbedFactory.error(
                    "Incorrect! ❌",
                    f"The correct answer was: **{correct_answer}**"
                )

            for child in self.children:
                child.disabled = True

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=embed)

        return callback


class EightBallView(discord.ui.View):
    """Button-based 8ball game"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🔮 Ask the Magic 8-Ball", style=discord.ButtonStyle.primary, custom_id="8ball_ask")
    async def ask_8ball(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ask 8ball"""
        responses = [
            "Yes, definitely!", "It is certain.", "Without a doubt.",
            "Most likely.", "Outlook good.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.",
            "Cannot predict now.", "Don't count on it.",
            "My reply is no.", "Outlook not so good.", "Very doubtful."
        ]

        response = random.choice(responses)

        embed = EmbedFactory.create(
            title="🔮 Magic 8-Ball",
            description=f"{interaction.user.mention} asked the Magic 8-Ball...\n\n**Answer:** {response}",
            color=EmbedColor.INFO
        )

        await interaction.response.send_message(embed=embed)


class TriviaStartView(discord.ui.View):
    """Button to start trivia"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🧠 Play Trivia", style=discord.ButtonStyle.success, custom_id="trivia_start")
    async def start_trivia(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start a trivia game"""
        question_data = random.choice(self.cog.trivia_questions)

        embed = EmbedFactory.create(
            title="🎯 Trivia Time!",
            description=f"**{question_data['question']}**",
            color=EmbedColor.INFO
        )
        embed.set_footer(text="You have 30 seconds to answer! Win 💎 50 for correct answer!")

        view = TriviaView(self.cog, question_data)
        await interaction.response.send_message(embed=embed, view=view)


class Games(commands.Cog):
    """Games and entertainment cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('games', {})
        self.trivia_questions = self._load_trivia()

    def _load_trivia(self):
        """Load trivia questions"""
        return [
            {
                "question": "What year was Python first released?",
                "options": ["1989", "1991", "1995", "2000"],
                "answer": 1
            },
            {
                "question": "What does CPU stand for?",
                "options": ["Central Processing Unit", "Computer Personal Unit", "Central Process Union", "Computer Processing Unit"],
                "answer": 0
            },
            {
                "question": "Who created Linux?",
                "options": ["Bill Gates", "Linus Torvalds", "Steve Jobs", "Dennis Ritchie"],
                "answer": 1
            },
            {
                "question": "What is the maximum value of a 32-bit signed integer?",
                "options": ["2,147,483,647", "4,294,967,295", "65,535", "2,147,483,648"],
                "answer": 0
            },
            {
                "question": "Which programming language is known as the 'mother of all languages'?",
                "options": ["C", "Assembly", "Fortran", "COBOL"],
                "answer": 0
            },
            {
                "question": "What does HTML stand for?",
                "options": ["Hyper Text Markup Language", "High Tech Modern Language", "Home Tool Markup Language", "Hyperlinks and Text Markup Language"],
                "answer": 0
            },
            {
                "question": "Who is known as the father of computers?",
                "options": ["Charles Babbage", "Alan Turing", "Bill Gates", "Steve Jobs"],
                "answer": 0
            },
            {
                "question": "What year was the first iPhone released?",
                "options": ["2005", "2006", "2007", "2008"],
                "answer": 2
            },
            {
                "question": "What does RAM stand for?",
                "options": ["Random Access Memory", "Read Access Memory", "Rapid Access Memory", "Run Access Memory"],
                "answer": 0
            },
            {
                "question": "Which company created JavaScript?",
                "options": ["Microsoft", "Netscape", "Google", "Apple"],
                "answer": 1
            },
            {
                "question": "What is the capital of France?",
                "options": ["London", "Berlin", "Paris", "Madrid"],
                "answer": 2
            },
            {
                "question": "How many continents are there?",
                "options": ["5", "6", "7", "8"],
                "answer": 2
            },
            {
                "question": "What is the largest planet in our solar system?",
                "options": ["Earth", "Mars", "Jupiter", "Saturn"],
                "answer": 2
            },
            {
                "question": "Who painted the Mona Lisa?",
                "options": ["Vincent van Gogh", "Pablo Picasso", "Leonardo da Vinci", "Michelangelo"],
                "answer": 2
            },
            {
                "question": "What is the speed of light?",
                "options": ["299,792 km/s", "150,000 km/s", "500,000 km/s", "1,000,000 km/s"],
                "answer": 0
            }
        ]

    @app_commands.command(name="setup-game-panel", description="Setup game panel with buttons for users (Admin)")
    @is_admin()
    async def setup_game_panel(self, interaction: discord.Interaction):
        """Setup game panel"""
        embed = EmbedFactory.create(
            title="🎮 Game Center",
            description="Click the buttons below to play games!\n\n"
                       "🎲 **Dice** - Roll a dice\n"
                       "🪙 **Coinflip** - Flip a coin\n"
                       "🧠 **Trivia** - Test your knowledge (Win 💎 50!)\n"
                       "🔮 **8-Ball** - Ask a question",
            color=EmbedColor.INFO
        )

        # Create dice panel
        await interaction.channel.send(embed=embed)

        # Dice game
        dice_embed = EmbedFactory.create(title="🎲 Dice Game", description="Click to roll a dice!", color=EmbedColor.INFO)
        await interaction.channel.send(embed=dice_embed, view=DiceGameView(self))

        # Coinflip game
        coin_embed = EmbedFactory.create(title="🪙 Coinflip", description="Pick heads or tails!", color=EmbedColor.INFO)
        await interaction.channel.send(embed=coin_embed, view=CoinFlipView(self))

        # Trivia game
        trivia_embed = EmbedFactory.create(title="🧠 Trivia Game", description="Test your knowledge! Win 💎 50!", color=EmbedColor.SUCCESS)
        await interaction.channel.send(embed=trivia_embed, view=TriviaStartView(self))

        # 8-Ball
        ball_embed = EmbedFactory.create(title="🔮 Magic 8-Ball", description="Ask the magic 8-ball a question!", color=EmbedColor.INFO)
        await interaction.channel.send(embed=ball_embed, view=EightBallView(self))

        await interaction.response.send_message(
            embed=EmbedFactory.success("Game Panel Created", "Users can now play games by clicking buttons!"),
            ephemeral=True
        )

        logger.info(f"Game panel created in {interaction.guild}")

    # Public commands for viewing stats
    @app_commands.command(name="rank", description="View your rank card")
    @app_commands.describe(user="User to check (optional)")
    async def rank(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View rank card - PUBLIC"""
        target = user or interaction.user

        user_data = await self.db.get_user(target.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(target.id, interaction.guild.id)

        leaderboard = await self.db.get_leaderboard(interaction.guild.id, limit=1000)
        rank = next((i + 1 for i, u in enumerate(leaderboard) if u['user_id'] == target.id), 0)

        from utils.constants import calculate_level_xp
        level = user_data.get('level', 0)
        xp = user_data.get('xp', 0)
        next_level_xp = calculate_level_xp(level + 1)

        embed = EmbedFactory.rank_card(target, level, xp, rank, next_level_xp)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balance", description="Check your balance")
    @app_commands.describe(user="User to check (optional)")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Check balance - PUBLIC"""
        target = user or interaction.user

        user_data = await self.db.get_user(target.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(target.id, interaction.guild.id)

        balance = user_data.get('balance', 0)
        embed = EmbedFactory.economy_balance(target, balance, "💎")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View server leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        """View leaderboard - PUBLIC"""
        leaderboard = await self.db.get_leaderboard(interaction.guild.id, limit=10)

        if not leaderboard:
            await interaction.response.send_message(
                embed=EmbedFactory.info("No Data", "No leaderboard data available"),
                ephemeral=True
            )
            return

        embed = EmbedFactory.leaderboard("XP Leaderboard", leaderboard, field_name="xp", color=EmbedColor.LEVELING)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Games(bot, bot.db, bot.config))
