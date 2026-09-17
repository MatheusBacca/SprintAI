import { defineStore } from 'pinia'

/**
 * Um número só para "o espelho mudou, mostre de novo".
 *
 * Antes cada tela inventava o próprio gatilho — a Home ouvia o stream, a Semana e a
 * Sprint olhavam o `last_run.id` do polling, e Contextos e Lembretes não olhavam nada.
 * Resultado: com o painel da tarefa aberto, um sync passava sem ninguém recarregar.
 *
 * Agora quem observa `revision` recarrega: as telas e também os painéis abertos.
 * O `AppShell` é o único lugar que alimenta isto.
 */
export const useRefreshStore = defineStore('refresh', {
  state: () => ({
    revision: 0,
    at: null,
    /** 'sync' ou 'manual' — a tela pode contar ao dev por que recarregou. */
    reason: null,
    lastRunId: null,
  }),
  actions: {
    /**
     * Fim de uma sincronização. O id chega por dois caminhos (o stream avisa na
     * hora, o polling do status é a rede de segurança quando ele cai) — sem
     * comparar o id, a mesma execução recarregaria tudo duas vezes.
     */
    afterSync(runId = null) {
      if (runId != null && runId === this.lastRunId) return
      this.lastRunId = runId
      this.bump('sync')
    },

    /** Botão "Recarregar": recarrega mesmo que nada tenha mudado no espelho. */
    reload() {
      this.bump('manual')
    },

    bump(reason) {
      this.revision += 1
      this.at = Date.now()
      this.reason = reason
    },
  },
})
