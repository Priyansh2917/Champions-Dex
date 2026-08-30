from typing import TYPE_CHECKING

import discord

from ballsdex.core.utils.menus.bulk_selector import BaseBulkSelector
from bd_models.models import BallInstance
from settings.models import settings

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from ballsdex.core.bot import BallsDexBot

    from .cog import BettingCog

type Interaction = discord.Interaction["BallsDexBot"]


class BetBulkSelector(BaseBulkSelector):
    async def configure(self, bot: "BallsDexBot", cog: "BettingCog", queryset: "QuerySet[BallInstance]"):
        self.cog = cog
        await super().configure(
            bot,
            queryset,
            header=f"## Bet bulk selection\nYour selected {settings.plural_collectible_name} are shown below.",
            description="-# Use the drop-down menu below to select your items.",
            select_placeholder=f"Select {settings.plural_collectible_name} to add",
            confirm_label="Add to bet",
        )

    async def on_confirm(self, interaction: Interaction, selected_ids: set[int]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        channel_id = interaction.channel.id if interaction.channel else 0
        if channel_id not in self.cog.active_bets:
            return await interaction.followup.send("No active bet in this channel.", ephemeral=True)

        bet_view = self.cog.active_bets[channel_id]
        if bet_view.state != "OPEN":
            return await interaction.followup.send("The bet is no longer open for additions.", ephemeral=True)

        user_id = interaction.user.id
        if user_id not in bet_view.participants:
            bet_view.participants.append(user_id)
        if user_id not in bet_view.holdings:
            bet_view.holdings[user_id] = []

        if not selected_ids:
            return await interaction.followup.send(
                f"You have not selected any {settings.plural_collectible_name} to add.",
                ephemeral=True,
            )

        balls_to_add = []
        async for ball in BallInstance.objects.filter(id__in=selected_ids):
            if ball.is_tradeable is False:
                return await interaction.followup.send(
                    f"{settings.collectible_name.title()} #{ball.pk:0X} is not tradeable.",
                    ephemeral=True,
                )
            if await ball.is_locked():
                return await interaction.followup.send(
                    f"{settings.collectible_name.title()} #{ball.pk:0X} is locked for trade/donation.",
                    ephemeral=True,
                )
            balls_to_add.append(ball)

        # Disable the selector view
        assert self.view
        self.view.stop()
        for children in self.view.walk_children():
            if hasattr(children, "disabled"):
                children.disabled = True  # type: ignore
        await interaction.edit_original_response(view=self.view)

        for ball in balls_to_add:
            bet_view.holdings[user_id].append(ball)
            await ball.lock_for_trade()

        grammar = (
            f"{settings.collectible_name}"
            if len(balls_to_add) == 1
            else f"{settings.plural_collectible_name}"
        )
        await interaction.followup.send(
            f"{len(balls_to_add)} {grammar} added to your bet pool.", ephemeral=True
        )
        
        await bet_view.update_message()
