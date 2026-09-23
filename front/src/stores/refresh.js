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
    /** 'sync', 'manual' ou 'jira' — a tela pode contar ao dev por que recarregou. */
    reason: null,
    lastRunId: null,
    recentWrites: [],
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

    /**
     * O dev mudou status ou Story Points pelo SprintAI. O aviso chega pela resposta, na
     * aba que escreveu, e pelo stream (`issue.changed`), que avisa também as outras abas
     * — o id da escrita desempata, como o da execução no fim do sync. Guarda alguns ids
     * e não só o último: duas escritas seguidas podem chegar intercaladas pelos dois
     * caminhos.
     */
    afterWrite(writeId = null) {
      if (writeId != null) {
        if (this.recentWrites.includes(writeId)) return
        this.recentWrites = [...this.recentWrites.slice(-19), writeId]
      }
      this.bump('jira')
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
