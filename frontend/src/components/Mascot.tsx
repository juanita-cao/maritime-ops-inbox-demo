// A small seal (first drawn as a dolphin) in the sidebar that shows how much is waiting [AMENDMENT 2026-09-26 UI round
// U11, owner]: many to-dos, tired with smoke over its head; some, calm and floating; few, eating a
// fish. A click plays a random move and a short dolphin-like chirp. Drawn here (SVG and CSS) and
// the sound is synthesised with Web Audio, so no third-party art or audio files are used.
import { useRef, useState } from 'react'
import { moodOf, type Mood } from '../vm/mascot'


const MOVES = ['jump', 'spin', 'wiggle', 'flip', 'sidestep', 'shake', 'headbob', 'slip'] as const
const WORDS = ['Eee-eee!', 'Hi!', 'You got this!', 'Splash!', 'Click-click!', 'Fish?']
const LABEL: Record<Mood, string> = { tired: 'So much to do…', calm: 'All calm', eating: 'Snack time' }

const BLUE = '#5AA8D6'
const DARK = '#3F8DBB'
const NAVY = '#1F3A68'
const BELLY = '#D8EEF8'
const INK = '#14202B'

function chirp() {
  try {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new AudioCtx()
    const now = ctx.currentTime
    const calls = 1 + Math.floor(Math.random() * 3)
    for (let i = 0; i < calls; i++) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      const start = now + i * 0.13
      const base = 900 + Math.random() * 700
      osc.type = 'sine'
      osc.frequency.setValueAtTime(base, start)
      osc.frequency.exponentialRampToValueAtTime(base * (1.6 + Math.random()), start + 0.08)
      osc.frequency.exponentialRampToValueAtTime(base * 0.9, start + 0.12)
      gain.gain.setValueAtTime(0.0001, start)
      gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.12)
      osc.connect(gain).connect(ctx.destination)
      osc.start(start)
      osc.stop(start + 0.13)
    }
    setTimeout(() => ctx.close(), 800)
  } catch {
    // no audio in this browser: the move still plays
  }
}

const CSS = `
.mm-dolphin { animation: mm-bob 3s ease-in-out infinite; transform-origin: 60px 112px; transform-box: view-box; }
.mm-calm .mm-eyes { animation: mm-blink 3s ease-in-out infinite; transform-origin: 49px 48px; transform-box: view-box; }
.mm-tired .mm-dolphin { animation: mm-sag 4s ease-in-out infinite; }
.mm-eating .mm-jaw { animation: mm-chew .45s ease-in-out infinite; transform-origin: 60px 72px; transform-box: view-box; }
.mm-fish { animation: mm-nibble .9s ease-in-out infinite; }
.mm-smoke { animation: mm-smoke 2.4s ease-out infinite; opacity: 0; transform-box: fill-box; transform-origin: center; }
.mm-smoke.s2 { animation-delay: .8s; } .mm-smoke.s3 { animation-delay: 1.6s; }
.mm-move-jump .mm-dolphin { animation: mm-jump .9s ease-out; }
.mm-move-spin .mm-dolphin { animation: mm-spin .9s ease-in-out; }
.mm-move-wiggle .mm-dolphin { animation: mm-wiggle .9s ease-in-out; }
.mm-move-flip .mm-dolphin { animation: mm-flip .9s ease-in-out; }
.mm-move-sidestep .mm-dolphin { animation: mm-sidestep 1.1s ease-in-out; }
.mm-move-shake .mm-dolphin { animation: mm-shake 1.1s linear; }
.mm-move-headbob .mm-head { animation: mm-headbob 1.2s ease-in-out; }
.mm-move-slip .mm-dolphin { animation: mm-slip 1.1s cubic-bezier(.3,.7,.4,1); }
.mm-move-slip .mm-head { animation: mm-wobble 1.1s ease-in-out; }
.mm-head { transform-box: view-box; transform-origin: 60px 76px; }
.mm-drops { opacity: 0; }
.mm-move-shake .mm-drops { animation: mm-drops 1.1s ease-out; }
.mm-bubble { animation: mm-pop 1.4s ease-out forwards; }
@keyframes mm-blink { 0%,76%,86%,100% { transform: scaleY(1) } 81% { transform: scaleY(.08) } }
@keyframes mm-bob { 0%,100% { transform: translateY(0) rotate(-2deg) } 50% { transform: translateY(-4px) rotate(2deg) } }
@keyframes mm-sag { 0%,100% { transform: translateY(2px) rotate(-3deg) } 50% { transform: translateY(4px) rotate(3deg) } }
@keyframes mm-chew { 0%,100% { transform: scaleY(1) } 50% { transform: scaleY(.3) } }
@keyframes mm-nibble { 0%,100% { transform: translate(48px,74px) } 50% { transform: translate(48px,72px) } }
@keyframes mm-smoke { 0% { opacity: 0; transform: translate(0,14px) scale(.5) } 25% { opacity: .85 } 100% { opacity: 0; transform: translate(4px,-10px) scale(1.25) } }
@keyframes mm-jump { 0% { transform: translateY(0) } 40% { transform: translateY(-26px) rotate(-18deg) } 70% { transform: translateY(-8px) rotate(10deg) } 100% { transform: translateY(0) } }
@keyframes mm-spin { 0% { transform: rotate(0) } 100% { transform: rotate(360deg) } }
@keyframes mm-wiggle { 0%,100% { transform: rotate(0) } 20% { transform: rotate(-14deg) } 40% { transform: rotate(12deg) } 60% { transform: rotate(-10deg) } 80% { transform: rotate(8deg) } }
@keyframes mm-flip { 0% { transform: scaleX(1) } 50% { transform: scaleX(-1) translateY(-10px) } 100% { transform: scaleX(1) } }
@keyframes mm-sidestep { 0%,100% { transform: translateX(0) rotate(0) } 18% { transform: translateX(-14px) rotate(-10deg) } 32% { transform: translateX(-14px) rotate(-4deg) } 50% { transform: translateX(0) rotate(0) } 68% { transform: translateX(14px) rotate(10deg) } 82% { transform: translateX(14px) rotate(4deg) } }
@keyframes mm-shake { 0% { transform: scale(1,1) } 10% { transform: scale(1.08,.9) } 15% { transform: rotate(-7deg) translateX(-2px) } 22% { transform: rotate(7deg) translateX(2px) } 29% { transform: rotate(-7deg) translateX(-2px) } 36% { transform: rotate(7deg) translateX(2px) } 43% { transform: rotate(-6deg) translateX(-2px) } 50% { transform: rotate(6deg) translateX(2px) } 57% { transform: rotate(-5deg) } 64% { transform: rotate(5deg) } 71% { transform: rotate(-3deg) } 78% { transform: rotate(3deg) } 90%,100% { transform: rotate(0) scale(1,1) } }
@keyframes mm-headbob { 0%,100% { transform: rotate(0) } 15% { transform: rotate(-16deg) } 35% { transform: rotate(14deg) } 55% { transform: rotate(-12deg) } 75% { transform: rotate(10deg) } 90% { transform: rotate(-3deg) } }
@keyframes mm-slip { 0% { transform: translateX(0) rotate(0) } 12% { transform: translateX(-18px) rotate(16deg) } 22% { transform: translateX(-20px) rotate(20deg) translateY(2px) } 34% { transform: translateX(3px) rotate(-8deg) } 46% { transform: translateX(-2px) rotate(5deg) } 58% { transform: translateX(1px) rotate(-3deg) } 72% { transform: rotate(1.5deg) } 100% { transform: translateX(0) rotate(0) } }
@keyframes mm-wobble { 0%,100% { transform: rotate(0) } 10% { transform: rotate(-20deg) } 22% { transform: rotate(18deg) } 34% { transform: rotate(-16deg) } 46% { transform: rotate(12deg) } 58% { transform: rotate(-8deg) } 72% { transform: rotate(5deg) } 86% { transform: rotate(-2deg) } }
@keyframes mm-drops { 0% { opacity: 0; transform: scale(.4) } 20% { opacity: 1 } 100% { opacity: 0; transform: scale(1.5) } }
@keyframes mm-pop { 0% { opacity: 0; transform: translateY(4px) scale(.8) } 15% { opacity: 1; transform: translateY(0) scale(1) } 80% { opacity: 1 } 100% { opacity: 0; transform: translateY(-6px) } }
@media (prefers-reduced-motion: reduce) { .mm-root * { animation: none !important; } }
`

export function Mascot({ todo }: { todo: number }) {
  const mood = moodOf(todo)
  const [move, setMove] = useState<string | null>(null)
  const [word, setWord] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const play = () => {
    const m = MOVES[Math.floor(Math.random() * MOVES.length)]
    setMove(null)
    requestAnimationFrame(() => setMove(m))
    setWord(WORDS[Math.floor(Math.random() * WORDS.length)])
    chirp()
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setMove(null)
      setWord(null)
    }, 1400)
  }

  return (
    <div className={`mm-root mm-${mood} ${move ? `mm-move-${move}` : ''}`} style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '4px 0 8px' }}>
      <style>{CSS}</style>
      {word && (
        <span className="mm-bubble" style={{ position: 'absolute', top: -6, right: 18, fontSize: 11, fontWeight: 600, background: '#FFFFFF', color: INK, border: '1px solid #D9E0E9', borderRadius: 10, padding: '1px 8px', whiteSpace: 'nowrap' }}>
          {word}
        </span>
      )}
      <button type="button" onClick={play} aria-label={`Seal: ${LABEL[mood]}, ${todo} to-dos. Click to play`}
        style={{ border: 0, background: 'transparent', padding: 0, cursor: 'pointer', lineHeight: 0 }}>
        <svg width="112" height="120" viewBox="0 -16 120 136" aria-hidden="true">
          {/* smoke puffs over the head when tired */}
          {mood === 'tired' && (
            <g fill="#8E9BA8">
              <g className="mm-smoke"><circle cx="56" cy="6" r="6" /><circle cx="63" cy="3" r="7" /><circle cx="70" cy="7" r="5" /></g>
              <g className="mm-smoke s2"><circle cx="48" cy="2" r="5" /><circle cx="54" cy="-2" r="6" /><circle cx="60" cy="2" r="4.5" /></g>
              <g className="mm-smoke s3"><circle cx="66" cy="0" r="5" /><circle cx="72" cy="-4" r="6" /><circle cx="78" cy="0" r="4.5" /></g>
            </g>
          )}
          <g className="mm-drops" fill="#8FC3E6" style={{ transformBox: 'view-box', transformOrigin: '60px 70px' }}>
            <circle cx="24" cy="54" r="2.4" /><circle cx="96" cy="50" r="2.4" /><circle cx="20" cy="84" r="2" />
            <circle cx="100" cy="82" r="2" /><circle cx="34" cy="30" r="1.8" /><circle cx="88" cy="28" r="1.8" />
          </g>
          <g className="mm-dolphin">
            {/* trousers and shoes */}
            <path d="M42 98 h36 v12 h-15 v-6 h-6 v6 h-15 z" fill={NAVY} />
            <ellipse cx="49" cy="113" rx="9" ry="4.5" fill={INK} />
            <ellipse cx="71" cy="113" rx="9" ry="4.5" fill={INK} />
            {/* striped sailor shirt with a collar */}
            <defs>
              <clipPath id="mm-shirt"><ellipse cx="60" cy="88" rx="22" ry="17" /></clipPath>
            </defs>
            <g clipPath="url(#mm-shirt)">
              <rect x="36" y="70" width="48" height="36" fill="#FFFFFF" />
              {[76, 83, 90, 97, 104].map((y) => <rect key={y} x="36" y={y} width="48" height="3.4" fill={NAVY} />)}
            </g>
            <path d="M47 73 l13 12 l13 -12 z" fill={NAVY} />
            <path d="M53 76 l7 6 l7 -6" fill="none" stroke="#FFFFFF" strokeWidth="1.2" />
            {/* flipper arms: down when tired, relaxed when calm, holding the fish when eating */}
            {mood === 'eating' ? (
              <g fill={DARK}>
                <path d="M40 84 q-6 -10 6 -16 q4 4 2 10 z" />
                <path d="M80 84 q6 -10 -6 -16 q-4 4 -2 10 z" />
              </g>
            ) : mood === 'tired' ? (
              <g fill={DARK}>
                <path d="M40 82 q-8 10 -6 24 q6 -4 9 -16 z" />
                <path d="M80 82 q8 10 6 24 q-6 -4 -9 -16 z" />
              </g>
            ) : (
              <g fill={DARK}>
                <path d="M40 82 q-14 4 -16 14 q10 0 18 -7 z" />
                <path d="M80 82 q14 4 16 14 q-10 0 -18 -7 z" />
              </g>
            )}
            <g className="mm-head">
            {/* head */}
            <circle cx="60" cy="50" r="28" fill={BLUE} />
            <ellipse cx="60" cy="60" rx="19" ry="13" fill={BELLY} />
            {/* sailor cap with an anchor badge */}
            <ellipse cx="60" cy="25" rx="24" ry="10" fill="#FFFFFF" stroke="#D9E0E9" strokeWidth="1" />
            <rect x="38" y="26" width="44" height="7" rx="3" fill={NAVY} />
            <circle cx="60" cy="24" r="4.2" fill="#C8402F" />
            <g fill="none" stroke="#FFFFFF" strokeWidth="0.9" strokeLinecap="round">
              <circle cx="60" cy="21.4" r="0.8" />
              <path d="M60 22.2 v4.6 M58.2 23.3 h3.6 M57.6 25.2 q2.4 2.8 4.8 0" />
            </g>
            {/* seal face [U12]: spots on the head, whisker pads with dots, a small nose, whiskers */}
            <g fill={DARK} opacity={0.55}>
              <circle cx="37" cy="45" r="2.2" /><circle cx="34" cy="53" r="1.6" /><circle cx="41" cy="38" r="1.5" />
              <circle cx="83" cy="45" r="2.2" /><circle cx="86" cy="53" r="1.6" /><circle cx="79" cy="38" r="1.5" />
            </g>
            <ellipse cx="54.5" cy="64" rx="6.8" ry="5.2" fill="#EEF8FD" stroke="#B9DCEE" strokeWidth="0.8" />
            <ellipse cx="65.5" cy="64" rx="6.8" ry="5.2" fill="#EEF8FD" stroke="#B9DCEE" strokeWidth="0.8" />
            <g fill={INK} opacity={0.45}>
              <circle cx="52" cy="63" r="0.7" /><circle cx="55" cy="65.5" r="0.7" /><circle cx="51.5" cy="66.5" r="0.7" />
              <circle cx="68" cy="63" r="0.7" /><circle cx="65" cy="65.5" r="0.7" /><circle cx="68.5" cy="66.5" r="0.7" />
            </g>
            <g stroke={INK} strokeWidth="0.8" strokeLinecap="round" opacity={0.6}>
              <path d="M48 62 L37 59 M48 64.5 L36 64.5 M48.5 67 L37.5 70" />
              <path d="M72 62 L83 59 M72 64.5 L84 64.5 M71.5 67 L82.5 70" />
            </g>
            <path d="M56.8 59.4 q3.2 -1.6 6.4 0 q-1 3.2 -3.2 3.8 q-2.2 -.6 -3.2 -3.8 z" fill={INK} />
            {/* eyes */}
            {mood === 'tired' ? (
              <g fill="none" stroke={INK} strokeWidth="2.2" strokeLinecap="round">
                <path d="M44 50 q5 4 10 0" />
                <path d="M66 50 q5 4 10 0" />
              </g>
            ) : mood === 'eating' ? (
              <g fill="none" stroke={INK} strokeWidth="2.2" strokeLinecap="round">
                <path d="M44 50 q5 -5 10 0" />
                <path d="M66 50 q5 -5 10 0" />
              </g>
            ) : (
              <g>
                {/* the left eye (as seen) winks */}
                <g className="mm-eyes">
                  <ellipse cx="49" cy="48" rx="4.2" ry="5.2" fill={INK} />
                  <circle cx="50.5" cy="46" r="1.5" fill="#FFFFFF" />
                </g>
                <ellipse cx="71" cy="48" rx="4.2" ry="5.2" fill={INK} />
                <circle cx="72.5" cy="46" r="1.5" fill="#FFFFFF" />
              </g>
            )}
            {/* cheeks */}
            {mood !== 'tired' && (
              <g fill="#F4A7B9" opacity={0.8}>
                <ellipse cx="41" cy="58" rx="4" ry="2.4" />
                <ellipse cx="79" cy="58" rx="4" ry="2.4" />
              </g>
            )}
            {/* mouth */}
            {mood === 'tired' ? (
              <path d="M55.5 72.5 q4.5 -3 9 0" fill="none" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
            ) : mood === 'eating' ? (
              <ellipse className="mm-jaw" cx="60" cy="72" rx="3.6" ry="2.8" fill="#7A3B4A" />
            ) : (
              <path d="M55 70.5 q5 4.5 10 0" fill="#E0707A" stroke={INK} strokeWidth="1.6" strokeLinecap="round" />
            )}
            {/* sweat drop when tired */}
            {mood === 'tired' && <path d="M85 34 q4 6 0 9 q-4 -3 0 -9 z" fill="#8FC3E6" />}
            </g>
            {/* the fish, held at the mouth */}
            {mood === 'eating' && (
              <g className="mm-fish" transform="translate(48 74)">
                <path d="M0 6 q10 -9 20 0 q-10 9 -20 0 z" fill="#F2A541" />
                <path d="M20 6 l6 -5 v10 z" fill="#F2A541" />
                <circle cx="5" cy="5" r="1.2" fill={INK} />
              </g>
            )}
          </g>
        </svg>
      </button>
    </div>
  )
}
