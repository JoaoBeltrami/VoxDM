"""
Configuração de VAD (Voice Activity Detection) para o pipeline de STT.

Por que existe: centraliza parâmetros de VAD passados ao AudioToTextRecorder —
evita valores mágicos espalhados pelo código e facilita tuning de sensibilidade.
Dependências: nenhuma direta — o VAD real é executado dentro do RealtimeSTT.
Armadilha: NÃO instanciar VAD separado — RealtimeSTT usa Silero + WebRTC
internamente; duplicar causa conflito de threads de áudio.

Exemplo:
    from engine.voice.vad import VAD_CONFIG
    recorder = AudioToTextRecorder(**VAD_CONFIG, model="tiny")
"""

# Parâmetros passados diretamente ao AudioToTextRecorder do RealtimeSTT.
# Ajustar silero_sensitivity e post_speech_silence_duration se o sistema
# cortar fala no meio de frases longas durante testes.
VAD_CONFIG: dict[str, object] = {
    # Sensibilidade do modelo Silero VAD (0.0 = menos sensível, 1.0 = mais)
    # Valor 0.4 equilibra detecção de voz suave com rejeição de ruído ambiente
    "silero_sensitivity": 0.4,
    # Sensibilidade do WebRTC VAD (0 = menos agressivo, 3 = mais agressivo)
    # Valor 3 rejeita melhor sons não-vocais (digitação, música de fundo)
    "webrtc_sensitivity": 3,
    # Gravação mínima para evitar transcrições de sons acidentais (segundos)
    "min_length_of_recording": 0.5,
    # Buffer capturado antes do VAD confirmar início de fala (segundos)
    # Evita cortar o início da primeira sílaba
    "pre_recording_buffer_duration": 0.2,
    # Silêncio pós-fala necessário para confirmar fim da frase (segundos)
    # Aumentar para 0.6+ se o DM faz pausas dramáticas dentro da frase
    "post_speech_silence_duration": 0.4,
}
