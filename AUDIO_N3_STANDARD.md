# N3 Natural — Clínica do Sono

Versão canônica: `n3-20260831` • Perfil: `N3-C`.

Os 28 áudios de capítulos passam a usar uma master N3 separada em `audio/n3/`. A pasta `audio/n2/` permanece congelada como rollback e não deve voltar ao runtime.

Regras: Neural TTS pt-BR; voz `pt-BR-AntonioNeural`; mono 44,1 kHz; MP3 128 kbps; alvo -18 dBFS; pico <= -1,2 dBFS; compressão leve; unidades respiratórias sem alteração lexical; prosódia por intenção semântica; pausas variáveis derivadas do conteúdo; nenhum ambiente/Foley; proibição de TTS nativo do navegador.

O workflow N3 deve falhar se qualquer um dos 28 arquivos estiver ausente, se canal/sample rate estiver incorreto, se houver retorno de `speechSynthesis` ou se o player não apontar exclusivamente para `audio/n3/`.
