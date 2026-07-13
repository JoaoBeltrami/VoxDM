"use client";

/**
 * useWarmupStatus — o menu sabe se o Mestre já acordou (A6 boot UX, 12/07).
 *
 * Por que existe: o site abre antes da API terminar o warmup (embedder +
 *   whisper + TTS ~4s, ou nem estar de pé) — o jogador clicava em "Nova
 *   aventura" contra um backend que ainda não responde e via só erro. O hook
 *   polla GET /health a cada 2,5s até `warmup_pronto` e PARA (zero custo
 *   depois do boot). API fora do ar = continua tentando (ela pode subir
 *   depois do front, ordem comum no start.bat).
 * Armadilha: usar só em telas de ENTRADA (menu) — in-game a sessão já provou
 *   que a API está viva; re-gatear lá seria ruído.
 */

import { useEffect, useState } from "react";

import { obterHealth } from "@/lib/api";

const INTERVALO_MS = 2_500;

export function useWarmupStatus(): { pronto: boolean; apiOnline: boolean } {
  const [pronto, setPronto] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);

  useEffect(() => {
    let vivo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const checar = async () => {
      const h = await obterHealth();
      if (!vivo) return;
      if (h) {
        setApiOnline(true);
        if (h.warmup_pronto) {
          setPronto(true);
          return; // pronto é terminal — para de pollar
        }
      } else {
        setApiOnline(false);
      }
      timer = setTimeout(checar, INTERVALO_MS);
    };
    void checar();

    return () => {
      vivo = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return { pronto, apiOnline };
}
