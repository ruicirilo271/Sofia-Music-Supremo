let tracks = [];
let currentIndex = -1;
let player = null;
let playerReady = false;
let autoplayQueue = false;
let loadingVideo = false;
const DEFAULT_COVER = "/static/default-cover.svg";

const $ = (id) => document.getElementById(id);
const els = {
  statusCard: $("statusCard"),
  modeSelect: $("modeSelect"),
  genreInput: $("genreInput"),
  itunesGenreSelect: $("itunesGenreSelect"),
  itunesGenreBox: $("itunesGenreBox"),
  spotifyGenreBox: $("spotifyGenreBox"),
  searchBox: $("searchBox"),
  searchInput: $("searchInput"),
  marketSelect: $("marketSelect"),
  chips: $("chips"),
  loadBtn: $("loadBtn"),
  playAllBtn: $("playAllBtn"),
  prevBtn: $("prevBtn"),
  nextBtn: $("nextBtn"),
  stopBtn: $("stopBtn"),
  trackList: $("trackList"),
  listTitle: $("listTitle"),
  counter: $("counter"),
  message: $("message"),
  nowCover: $("nowCover"),
  nowTitle: $("nowTitle"),
  nowArtist: $("nowArtist"),
  nowSource: $("nowSource"),
  spotifyLink: $("spotifyLink"),
  itunesLink: $("itunesLink"),
  playerPlaceholder: $("playerPlaceholder"),
};

window.onYouTubeIframeAPIReady = function () {
  player = new YT.Player("player", {
    width: "100%",
    height: "100%",
    playerVars: {
      autoplay: 1,
      controls: 1,
      rel: 0,
      modestbranding: 1,
      playsinline: 1,
      origin: window.location.origin,
    },
    events: {
      onReady: () => { playerReady = true; },
      onStateChange: onPlayerStateChange,
      onError: onPlayerError,
    },
  });
};

function onPlayerStateChange(event) {
  if (event.data === YT.PlayerState.ENDED && autoplayQueue) {
    playNext();
  }
}

function onPlayerError() {
  showMessage("Este vídeo não deu para tocar/embeber. Vou tentar a próxima música.");
  if (autoplayQueue) setTimeout(playNext, 800);
}

async function fetchJson(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Erro HTTP ${res.status}`);
  }
  return data;
}

function showMessage(text, type = "warn") {
  els.message.textContent = text;
  els.message.classList.remove("hidden");
  if (type === "ok") {
    els.message.style.background = "rgba(68,255,168,.12)";
    els.message.style.borderColor = "rgba(68,255,168,.28)";
    els.message.style.color = "#baffdd";
  } else {
    els.message.style.background = "rgba(255,209,102,.12)";
    els.message.style.borderColor = "rgba(255,209,102,.28)";
    els.message.style.color = "#ffe6a0";
  }
}

function hideMessage() {
  els.message.classList.add("hidden");
}

function setLoading(isLoading) {
  document.body.classList.toggle("loading", isLoading);
  els.loadBtn.disabled = isLoading;
  els.playAllBtn.disabled = isLoading;
  els.loadBtn.textContent = isLoading ? "⏳ A carregar..." : "⚡ Carregar músicas";
}

function updateModeUi() {
  const mode = els.modeSelect.value;
  els.spotifyGenreBox.classList.toggle("hidden", mode !== "spotify_genre");
  els.searchBox.classList.toggle("hidden", mode !== "spotify_search");
  els.itunesGenreBox.classList.toggle("hidden", mode !== "itunes_genre");
  els.chips.classList.toggle("hidden", mode !== "spotify_genre");
  els.marketSelect.closest("label").classList.toggle("hidden", mode === "itunes_global" || mode === "itunes_pt" || mode === "itunes_genre");
}

async function checkStatus() {
  try {
    const status = await fetchJson("/api/status");
    const spotify = status.spotify_configured ? "Spotify OK" : "Falta Spotify";
    const youtube = status.youtube_configured ? "YouTube OK" : "Falta YouTube";
    els.statusCard.innerHTML = `<div class="pulse"></div><div><strong>${spotify} · ${youtube}</strong><small>iTunes/Apple não precisa de chave</small></div>`;
  } catch (err) {
    els.statusCard.innerHTML = `<div class="pulse"></div><div><strong>Erro ao verificar APIs</strong><small>${escapeHtml(err.message)}</small></div>`;
  }
}

async function loadItunesGenres() {
  try {
    const data = await fetchJson("/api/itunes/genres");
    els.itunesGenreSelect.innerHTML = data.genres.map(g => `<option value="${escapeAttr(g.id)}">${escapeHtml(g.name)}</option>`).join("");
    const world = data.genres.find(g => /world/i.test(g.name));
    if (world) els.itunesGenreSelect.value = world.id;
  } catch (err) {
    showMessage(`Não consegui carregar géneros iTunes: ${err.message}`);
  }
}

async function loadTracks() {
  hideMessage();
  setLoading(true);
  try {
    const mode = els.modeSelect.value;
    let url = "";
    let title = "";

    if (mode === "spotify_genre") {
      const genre = els.genreInput.value.trim() || "kizomba";
      const market = els.marketSelect.value;
      url = `/api/spotify/genre?genre=${encodeURIComponent(genre)}&market=${encodeURIComponent(market)}&limit=40`;
      title = `Top Spotify: ${genre}`;
    } else if (mode === "spotify_search") {
      const q = els.searchInput.value.trim();
      if (!q) throw new Error("Escreve uma música, artista ou género para pesquisar no Spotify.");
      const market = els.marketSelect.value;
      url = `/api/spotify/search?q=${encodeURIComponent(q)}&market=${encodeURIComponent(market)}&limit=40`;
      title = `Pesquisa Spotify: ${q}`;
    } else if (mode === "itunes_pt") {
      url = "/api/itunes/top?country=pt&limit=40";
      title = "Top Portugal iTunes/Apple";
    } else if (mode === "itunes_global") {
      url = "/api/itunes/global?limit=40";
      title = "Top Global iTunes/Apple";
    } else if (mode === "itunes_genre") {
      const genreId = els.itunesGenreSelect.value;
      const genreName = els.itunesGenreSelect.options[els.itunesGenreSelect.selectedIndex]?.text || "género";
      url = `/api/itunes/top?country=pt&genre_id=${encodeURIComponent(genreId)}&limit=40`;
      title = `iTunes Portugal: ${genreName}`;
    }

    const data = await fetchJson(url);
    tracks = data.items || [];
    currentIndex = -1;
    autoplayQueue = false;
    renderTracks(title);

    if (!tracks.length) {
      showMessage("Não vieram músicas. Experimenta outro género ou pesquisa.");
    } else {
      showMessage(`${tracks.length} músicas carregadas. Agora podes clicar em “Ouvir todas”.`, "ok");
    }
  } catch (err) {
    showMessage(err.message);
  } finally {
    setLoading(false);
  }
}

function renderTracks(title) {
  els.listTitle.textContent = title;
  els.counter.textContent = `${tracks.length} música${tracks.length === 1 ? "" : "s"}`;
  els.trackList.innerHTML = tracks.map((track, index) => trackCard(track, index)).join("");
  [...els.trackList.querySelectorAll(".track-card")].forEach(card => {
    card.addEventListener("click", () => {
      autoplayQueue = false;
      playTrack(Number(card.dataset.index));
    });
  });
}


function getCover(track) {
  return (track && track.cover && String(track.cover).trim()) ? track.cover : DEFAULT_COVER;
}

function trackCard(track, index) {
  const rank = track.rank ? `#${track.rank}` : `#${index + 1}`;
  const badge = track.source === "itunes" ? "iTunes" : `Spotify ${track.popularity || ""}`;
  return `
    <article class="track-card ${index === currentIndex ? "active" : ""}" data-index="${index}">
      <img src="${escapeAttr(getCover(track))}" alt="" loading="lazy" onerror="this.onerror=null;this.src='/static/default-cover.svg';">
      <div class="track-info">
        <div class="track-title">${escapeHtml(track.title)}</div>
        <div class="track-artist">${escapeHtml(track.artist)}</div>
        <div class="track-meta"><span class="badge">${escapeHtml(badge)}</span><span class="rank">${escapeHtml(rank)}</span></div>
      </div>
    </article>`;
}

async function playTrack(index) {
  if (!tracks.length) {
    showMessage("Primeiro carrega uma lista de músicas.");
    return;
  }
  if (index < 0 || index >= tracks.length) return;
  if (!playerReady || !player) {
    showMessage("O player do YouTube ainda está a iniciar. Tenta novamente em 1 segundo.");
    return;
  }
  if (loadingVideo) return;

  loadingVideo = true;
  currentIndex = index;
  const track = tracks[currentIndex];
  updateNowPlaying(track, "A procurar vídeo no YouTube...");
  renderTracks(els.listTitle.textContent);

  try {
    const q = track.youtube_query || `${track.artist} ${track.title} official audio`;
    const data = await fetchJson(`/api/youtube/search?q=${encodeURIComponent(q)}`);
    if (!data.video || !data.video.id) throw new Error("sem videoId");
    els.playerPlaceholder.classList.add("hidden");
    player.loadVideoById(data.video.id);
    updateNowPlaying(track, `YouTube: ${data.video.title || "vídeo encontrado"}`);
  } catch (err) {
    showMessage(`Não consegui abrir esta música no YouTube: ${err.message}`);
    if (autoplayQueue) setTimeout(playNext, 800);
  } finally {
    loadingVideo = false;
  }
}

function updateNowPlaying(track, sourceText) {
  els.nowCover.onerror = () => { els.nowCover.onerror = null; els.nowCover.src = DEFAULT_COVER; };
  els.nowCover.src = getCover(track);
  els.nowTitle.textContent = track.title || "Sem título";
  els.nowArtist.textContent = track.artist || "Artista desconhecido";
  els.nowSource.textContent = sourceText || track.source || "";

  setOptionalLink(els.spotifyLink, track.spotify_url);
  setOptionalLink(els.itunesLink, track.itunes_url);
}

function setOptionalLink(el, url) {
  if (url) {
    el.href = url;
    el.classList.remove("hidden");
  } else {
    el.removeAttribute("href");
    el.classList.add("hidden");
  }
}

function playAll() {
  if (!tracks.length) {
    loadTracks().then(() => {
      if (tracks.length) playAll();
    });
    return;
  }
  autoplayQueue = true;
  playTrack(currentIndex >= 0 ? currentIndex : 0);
}

function playNext() {
  if (!tracks.length) return;
  const next = currentIndex + 1;
  if (next >= tracks.length) {
    autoplayQueue = false;
    showMessage("Chegaste ao fim da lista.", "ok");
    return;
  }
  playTrack(next);
}

function playPrev() {
  if (!tracks.length) return;
  const prev = Math.max(0, currentIndex - 1);
  playTrack(prev);
}

function stopPlayback() {
  autoplayQueue = false;
  try { if (player && playerReady) player.stopVideo(); } catch (_) {}
  els.nowTitle.textContent = "Parado";
  els.nowArtist.textContent = "A fila continua carregada.";
  els.nowSource.textContent = "Carrega Play ou Ouvir todas para continuar.";
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/`/g, "&#96;");
}

els.modeSelect.addEventListener("change", updateModeUi);
els.loadBtn.addEventListener("click", loadTracks);
els.playAllBtn.addEventListener("click", playAll);
els.nextBtn.addEventListener("click", () => { autoplayQueue = false; playNext(); });
els.prevBtn.addEventListener("click", () => { autoplayQueue = false; playPrev(); });
els.stopBtn.addEventListener("click", stopPlayback);
els.searchInput.addEventListener("keydown", e => { if (e.key === "Enter") loadTracks(); });
els.genreInput.addEventListener("keydown", e => { if (e.key === "Enter") loadTracks(); });
els.chips.addEventListener("click", e => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  els.genreInput.value = btn.dataset.genre;
  els.modeSelect.value = "spotify_genre";
  updateModeUi();
  loadTracks();
});

updateModeUi();
checkStatus();
loadItunesGenres();
loadTracks();
