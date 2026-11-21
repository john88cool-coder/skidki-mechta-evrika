<!-- Заглушка карточки на время загрузки: те же размеры, что у DealCard. -->
<div class="sk-card" aria-hidden="true">
	<div class="sk-photo animate-pulse"></div>
	<div class="sk-body">
		<div class="sk-line w-24 animate-pulse"></div>
		<div class="sk-line w-full animate-pulse"></div>
		<div class="sk-line w-3/4 animate-pulse"></div>
		<div class="sk-line h-6 w-32 animate-pulse"></div>
		<div class="sk-line h-8 w-full animate-pulse"></div>
	</div>
</div>

<style>
	.sk-card {
		display: flex; flex-direction: column;
		background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden;
	}
	.sk-photo { height: 168px; margin: 8px 8px 0; border-radius: 12px; background: var(--paper-2); }
	.sk-body { display: grid; gap: 10px; padding: 12px 14px; }
	.sk-line { height: 14px; border-radius: 999px; background: var(--paper-3); }
	@media (max-width: 640px) {
		.sk-card { flex-direction: row; }
		.sk-photo { width: 104px; height: 128px; margin: 8px 0 8px 8px; flex-shrink: 0; }
		.sk-body { flex: 1; }
	}
</style>
