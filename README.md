# Sofia Music Supremo

App Flask para descobrir músicas no Spotify e nos tops iTunes/Apple Music, e ouvir pelo YouTube com fila contínua.

## Local

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

Abre: http://127.0.0.1:5000

## Vercel

A app está preparada para Vercel com `app.py` na raiz e `vercel.json` sem `functions`, para evitar erros do género `api/*.py doesn't match any Serverless Functions`.

No painel da Vercel, adiciona estas Environment Variables:

- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `YOUTUBE_API_KEY`
- `DEFAULT_MARKET` = `PT`
- `DEFAULT_LIMIT` = `40`

Depois faz deploy normalmente. O ficheiro `.env` é só para uso local e não deve ser enviado com chaves reais.

## Default cover

Existe uma capa local em `static/default-cover.svg`. A app usa esta imagem sempre que o Spotify/iTunes não devolver capa ou quando uma imagem externa falhar.
