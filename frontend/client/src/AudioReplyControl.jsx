import { useEffect, useRef, useState } from "react";

export default function AudioReplyControl({ audioUrl }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);

  useEffect(() => {
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    audio.onplay = () => { setPlaying(true); setHasStarted(true); };
    audio.onpause = () => setPlaying(false);
    audio.onended = () => setPlaying(false);
    audio.play().catch(() => {});
    return () => {
      audio.pause();
      audio.src = "";
      audioRef.current = null;
    };
  }, [audioUrl]);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      try { await audio.play(); } catch { /* browser may require a user gesture */ }
    } else {
      audio.pause();
    }
  }

  function replay() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    audio.play().catch(() => {});
  }

  return (
    <div className="audio-reply-controls" role="group" aria-label="Contrôles de la réponse vocale">
      <button className="replay-btn" type="button" onClick={togglePlayback}>
        {playing ? "❚❚ Pause" : hasStarted ? "▶ Reprendre" : "🔊 Écouter"}
      </button>
      {hasStarted && <button className="replay-btn replay-btn--secondary" type="button" onClick={replay}>↻ Réécouter</button>}
    </div>
  );
}
