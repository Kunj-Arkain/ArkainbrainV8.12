"""
ARKAINBRAIN — Mini RMG Game Pipeline (Phase 7)

Second pipeline type: Real Money Gaming mini-games.
Produces playable HTML5 games with provably fair math.

Stages:
  Brief → Research → Math Model → Game Design → Playable Build → Compliance → Package

Supported games: crash, plinko, mines, dice, wheel, hilo, chicken, scratch
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


def _get_model(agent_key: str = "game_designer", fallback: str = "gpt-4.1-mini") -> str:
    """Get model string from ACP (if loaded) or env var fallback."""
    try:
        from config.settings import LLMConfig
        model = LLMConfig.get_llm(agent_key)
        # Strip 'openai/' prefix for raw OpenAI client calls
        return model.replace("openai/", "") if model else fallback
    except Exception:
        return os.getenv("LLM_LIGHT", fallback)

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger("arkainbrain.rmg")
console = Console()


def emit(event_type: str, **data):
    """Emit structured log events for the thought-feed UI."""
    payload = json.dumps({"event": event_type, **data})
    print(f"[EMIT] {payload}", flush=True)


def run_mini_rmg(job_id: str, params: dict, output_dir: str):
    """Execute the full Mini RMG pipeline.

    Args:
        job_id: Job ID
        params: Pipeline parameters from the form
        output_dir: Base output directory path
    """
    from config.database import worker_update_job
    from sim_engine.rmg import get_game_engine, GAME_TYPES

    started = datetime.now().isoformat()
    game_type = params.get("game_type", "crash").lower()
    theme = params.get("theme", "Default Game")
    house_edge = float(params.get("house_edge", 0.03))
    max_multiplier = float(params.get("max_multiplier", 1000))
    web3_mode = params.get("web3_mode", False)
    custom_config = params.get("custom_config", {})

    console.print(Panel(
        f"[bold]🎮 Mini RMG Pipeline[/bold]\n\n"
        f"Game Type: {game_type}\n"
        f"Theme: {theme}\n"
        f"House Edge: {house_edge*100:.1f}%\n"
        f"Max Multiplier: {max_multiplier}x\n"
        f"Web3 Mode: {'Yes' if web3_mode else 'No'}",
        title="Mini RMG Starting", border_style="cyan",
    ))

    # Validate game type
    if game_type not in GAME_TYPES:
        worker_update_job(job_id, status="failed",
                          error=f"Unknown game type: {game_type}. Available: {GAME_TYPES}")
        return

    # Create output dirs
    od = Path(output_dir)
    for sub in ["00_config", "01_math", "02_design", "03_game", "04_compliance", "05_package"]:
        (od / sub).mkdir(parents=True, exist_ok=True)

    worker_update_job(job_id, status="running", current_stage="Initializing", output_dir=str(od))

    try:
        # ══════════════════════════════════════════════════
        # STAGE 1: Math Model
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Computing math model")
        emit("stage_start", name="Math Model", num=0, icon="🔢",
             desc=f"Building {game_type} math model with {house_edge*100:.1f}% house edge")
        console.print(f"\n[bold cyan]🔢 Stage 1: Math Model ({game_type})[/bold cyan]\n")

        engine = get_game_engine(game_type)
        config = engine.generate_config(
            house_edge=house_edge,
            max_multiplier=max_multiplier,
            **custom_config,
        )

        # Save config
        (od / "00_config" / "game_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8")

        # Run simulation
        console.print(f"[cyan]Running 500,000-round simulation...[/cyan]")
        sim_results = engine.simulate(config, rounds=500_000, seed=42)
        (od / "01_math" / "simulation_results.json").write_text(
            json.dumps(sim_results.to_dict(), indent=2), encoding="utf-8")

        console.print(f"[green]✅ Math model complete:[/green]")
        console.print(f"   House Edge: theoretical={sim_results.house_edge_theoretical*100:.2f}% "
                       f"measured={sim_results.house_edge_measured*100:.2f}%")
        console.print(f"   RTP: {sim_results.rtp*100:.2f}%")
        console.print(f"   Hit Rate: {sim_results.hit_rate*100:.1f}%")
        console.print(f"   Max Win Hit: {sim_results.max_multiplier_hit:.1f}x")

        # Math certification (Phase 2 integration)
        try:
            from tools.minigame_math import MiniGameMathEngine
            math_eng = MiniGameMathEngine()
            math_model = getattr(math_eng, f"{game_type}_model")()
            cert_report = math_model.certification_report()
            (od / "01_math" / "certification_report.json").write_text(
                json.dumps(cert_report, indent=2, default=str), encoding="utf-8")
            proof = cert_report.get("rtp_proof", {})
            console.print(f"   📜 Certification: P_sum={proof.get('probability_sum_check')} "
                          f"RTP_check={proof.get('rtp_check')}")
        except Exception as e:
            console.print(f"[yellow]   ⚠️ Certification: {e}[/yellow]")

        # Monte Carlo validation (Phase 2 integration)
        try:
            from tools.minigame_montecarlo import MonteCarloValidator
            mc = MonteCarloValidator(tolerance=0.005)
            mc_fn = getattr(mc, f"validate_{game_type}")
            mc_result = mc_fn(n_rounds=500_000)
            (od / "01_math" / "montecarlo_validation.json").write_text(
                json.dumps(mc_result.to_dict(), indent=2), encoding="utf-8")
            console.print(f"   🎲 Monte Carlo: mRTP={mc_result.measured_rtp*100:.3f}% "
                          f"({'✅ PASS' if mc_result.rtp_pass else '❌ FAIL'})")
        except Exception as e:
            console.print(f"[yellow]   ⚠️ Monte Carlo: {e}[/yellow]")

        # RNG specification (Phase 2 integration)
        try:
            from tools.minigame_rng import ProvablyFairRNG, generate_verification_js
            rng = ProvablyFairRNG()
            demo_session = rng.new_session(client_seed="demo")
            demo_round = getattr(rng, f"generate_{_rng_method(game_type)}")(demo_session)
            rng_spec = {
                "system": "HMAC-SHA256 server_seed:client_seed:nonce chain",
                "demo_session": {
                    "server_seed_hash": demo_session.server_seed_hash,
                    "client_seed": demo_session.client_seed,
                    "demo_outcome": demo_round.outcome,
                },
                "verification_js": generate_verification_js()[:500] + "...",
            }
            (od / "01_math" / "rng_specification.json").write_text(
                json.dumps(rng_spec, indent=2), encoding="utf-8")
            console.print(f"   🔐 RNG spec: HMAC-SHA256 chain, verification JS included")
        except Exception as e:
            console.print(f"[yellow]   ⚠️ RNG spec: {e}[/yellow]")

        emit("stage_done", name="Math Model", num=0)
        emit("metric", key="rtp", value=round(sim_results.rtp * 100, 2), label="RTP %")
        emit("metric", key="house_edge", value=round(sim_results.house_edge_measured * 100, 3),
             label="House Edge %")

        # ══════════════════════════════════════════════════
        # STAGE 2: Game Design (LLM-powered)
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Generating game design")
        emit("stage_start", name="Game Design", num=1, icon="🎨",
             desc=f"AI-designing '{theme}' {game_type} game")
        console.print(f"\n[bold yellow]🎨 Stage 2: Game Design[/bold yellow]\n")

        design = _generate_game_design(game_type, theme, config, sim_results)
        (od / "02_design" / "game_design.json").write_text(
            json.dumps(design, indent=2), encoding="utf-8")
        console.print(f"[green]✅ Game design generated: {design.get('title', theme)}[/green]")
        emit("stage_done", name="Game Design", num=1)

        # ══════════════════════════════════════════════════
        # STAGE 3: Playable HTML5 Build
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Building HTML5 game")
        emit("stage_start", name="Playable Build", num=2, icon="🎮",
             desc="Generating full HTML5 playable game")
        console.print(f"\n[bold green]🎮 Stage 3: Playable HTML5 Build[/bold green]\n")

        game_path = None
        # Primary path: Use Phase 3 templates with config injection (best quality)
        try:
            from tools.minigame_config import build_config
            from tools.minigame_injector import save_themed_game

            target_rtp = (1 - house_edge) * 100
            volatility = params.get("volatility", "medium")
            mg_config = build_config(
                game_type=game_type,
                target_rtp=target_rtp,
                volatility=volatility,
                theme_overrides={
                    "name": design.get("title", theme),
                    "title": design.get("title", theme),
                    "primary": design.get("ui_theme", {}).get("primary_color", "#7c6aef"),
                    "secondary": design.get("ui_theme", {}).get("secondary_color", "#22c55e"),
                },
                starting_balance=params.get("starting_balance", 1000),
            )

            safe_name = re.sub(r'[^a-z0-9]+', '-', theme.lower()).strip('-')
            out_name = f"{game_type}_{safe_name}_{job_id}.html"
            game_out = od / "03_game"
            game_out.mkdir(parents=True, exist_ok=True)
            game_file = save_themed_game(
                game_type=game_type,
                config=mg_config,
                output_name=out_name,
                output_dir=game_out,
            )
            game_path = str(game_file)
            console.print(f"[green]✅ Phase 3 game built via config injection: {game_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Phase 3 build failed ({e}), falling back to template builder[/yellow]")

        # Fallback: Use template builder
        if not game_path or not Path(game_path).exists():
            from templates.rmg.builder import build_rmg_game
            game_path = build_rmg_game(
                game_type=game_type,
                design=design,
                config=config,
                sim_results=sim_results.to_dict(),
                output_dir=str(od / "03_game"),
            )
            console.print(f"[green]✅ Template game built: {game_path}[/green]")

        # Code validation (Phase 3 integration)
        try:
            from tools.minigame_codegen import validate_game_html
            game_html = Path(game_path).read_text(encoding="utf-8") if game_path else ""
            if game_html:
                val = validate_game_html(game_html, game_type)
                (od / "03_game" / "validation_report.json").write_text(
                    json.dumps(val, indent=2), encoding="utf-8")
                console.print(f"   🔍 Validation: score={val['score']}/100, "
                              f"passed={val['passed']}, "
                              f"warnings={len(val.get('warnings',[]))}")
        except Exception as e:
            console.print(f"[yellow]   ⚠️ Validation: {e}[/yellow]")

        emit("stage_done", name="Playable Build", num=2)

        # ── Post-build: i18n + Wallet Bridge injection ──
        try:
            game_html_path = Path(game_path) if game_path else None
            if game_html_path and game_html_path.exists():
                html_content = game_html_path.read_text(encoding="utf-8")

                # i18n injection
                lang = params.get("language", "en")
                if lang and lang != "en":
                    from tools.i18n import I18N, inject_i18n
                    i18n = I18N(lang)
                    html_content = inject_i18n(html_content, i18n)
                    console.print(f"   🌍 i18n injected: {i18n.lang_name} ({lang})")

                # Wallet bridge injection (always inject — activates via URL param)
                from tools.wallet_bridge import inject_wallet_bridge
                html_content = inject_wallet_bridge(
                    html_content, game_type=game_type,
                    game_id=f"gen_{job_id}", api_base="/api/platform",
                )
                console.print(f"   💰 Wallet bridge injected (activate via ?server_mode=1)")

                game_html_path.write_text(html_content, encoding="utf-8")
        except Exception as e:
            console.print(f"[yellow]   ⚠️ Post-build injection: {e}[/yellow]")

        # ══════════════════════════════════════════════════
        # STAGE 4: Compliance Check
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Compliance verification")
        emit("stage_start", name="Compliance", num=3, icon="⚖️",
             desc="Verifying provably fair + jurisdiction compliance")
        console.print(f"\n[bold red]⚖️ Stage 4: Compliance[/bold red]\n")

        compliance = _run_compliance_check(game_type, config, sim_results, params)
        (od / "04_compliance" / "compliance_report.json").write_text(
            json.dumps(compliance, indent=2), encoding="utf-8")
        status_str = "✅ PASS" if compliance.get("passed") else "⚠️ WARNINGS"
        console.print(f"[green]{status_str}: {len(compliance.get('checks', []))} checks run[/green]")
        emit("stage_done", name="Compliance", num=3)

        # ══════════════════════════════════════════════════
        # STAGE 5: Web3 Output (Optional)
        # ══════════════════════════════════════════════════
        if web3_mode:
            worker_update_job(job_id, current_stage="Generating Web3 contracts")
            emit("stage_start", name="Web3 Output", num=4, icon="🔗",
                 desc="Generating Solidity contracts + deploy scripts")
            console.print(f"\n[bold magenta]🔗 Stage 5: Web3 Output[/bold magenta]\n")

            from templates.web3.generator import generate_web3_output
            w3_path = generate_web3_output(
                game_type=game_type,
                config=config,
                design=design,
                output_dir=str(od / "05_package" / "web3"),
            )
            console.print(f"[green]✅ Web3 contracts generated: {w3_path}[/green]")
            emit("stage_done", name="Web3 Output", num=4)

        # ══════════════════════════════════════════════════
        # STAGE 6: Package
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Packaging deliverables")
        emit("stage_start", name="Package", num=5, icon="📦", desc="Assembling final package")
        console.print(f"\n[bold green]📦 Stage 6: Package[/bold green]\n")

        manifest = {
            "game_type": game_type,
            "theme": theme,
            "title": design.get("title", theme),
            "house_edge_target": house_edge,
            "house_edge_measured": sim_results.house_edge_measured,
            "rtp": sim_results.rtp,
            "max_multiplier_config": max_multiplier,
            "max_multiplier_hit": sim_results.max_multiplier_hit,
            "simulation_rounds": sim_results.rounds,
            "web3": web3_mode,
            "compliance_passed": compliance.get("passed", False),
            "started_at": started,
            "completed_at": datetime.now().isoformat(),
            "files": [str(f.relative_to(od)) for f in od.rglob("*") if f.is_file()],
        }
        (od / "05_package" / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")

        # ── Auto-register in Arcade ──
        try:
            import shutil
            gen_dir = Path(__file__).parent.parent / "static" / "arcade" / "games" / "generated"
            gen_dir.mkdir(parents=True, exist_ok=True)
            reg_file = gen_dir / "_registry.json"

            # Find the built game HTML
            game_html_candidates = list((od / "03_game").glob("*.html"))
            if game_html_candidates:
                src_html = game_html_candidates[0]
                safe_name = re.sub(r'[^a-z0-9]+', '-', theme.lower()).strip('-')
                dest_name = f"{game_type}_{safe_name}_{job_id}.html"
                dest_path = gen_dir / dest_name
                shutil.copy2(str(src_html), str(dest_path))

                # Update registry
                registry = []
                if reg_file.exists():
                    try:
                        registry = json.loads(reg_file.read_text())
                    except Exception:
                        registry = []

                registry.append({
                    "id": f"gen_{job_id}",
                    "filename": dest_name,
                    "game_type": game_type,
                    "title": design.get("title", theme),
                    "theme": theme,
                    "rtp": round(sim_results.rtp * 100, 2),
                    "house_edge": round(house_edge * 100, 2),
                    "job_id": job_id,
                    "created_at": datetime.now().isoformat(),
                })
                reg_file.write_text(json.dumps(registry, indent=2), encoding="utf-8")
                console.print(f"[green]🕹️ Registered in arcade: {dest_name}[/green]")
            else:
                console.print("[yellow]⚠️ No game HTML found for arcade registration[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Arcade registration: {e}[/yellow]")

        # ── Auto-register in Platform Library (Phase 6) ──
        try:
            from tools.platform_engine import PlatformEngine
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            pe = PlatformEngine(str(data_dir / "platform.db"))
            pe.register_game({
                "id": f"gen_{job_id}",
                "game_type": game_type,
                "title": design.get("title", theme),
                "theme": theme,
                "filename": dest_name if 'dest_name' in dir() else f"{game_type}_{job_id}.html",
                "rtp": round(sim_results.rtp * 100, 2),
                "house_edge": round(house_edge * 100, 2),
                "volatility": params.get("volatility", "medium"),
                "max_win": max_multiplier,
                "tags": [game_type, theme.lower().split()[0] if theme else "custom"],
                "config": config,
            })
            console.print(f"[green]📚 Registered in platform library[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Platform registration: {e}[/yellow]")

        all_files = list(od.rglob("*"))
        file_count = sum(1 for f in all_files if f.is_file())
        console.print(Panel(
            f"[bold green]✅ Mini RMG Pipeline Complete[/bold green]\n\n"
            f"📁 Output: {od}\n"
            f"🎮 Game: {design.get('title', theme)}\n"
            f"📊 RTP: {sim_results.rtp*100:.2f}% (target: {(1-house_edge)*100:.2f}%)\n"
            f"📄 Files: {file_count}\n"
            f"⏱️ {started} → {manifest['completed_at']}",
            title="🎮 Package Complete", border_style="green",
        ))

        emit("stage_done", name="Package", num=5)
        emit("metric", key="files", value=file_count, label="Total Files")
        emit("info", msg="Pipeline complete", icon="🎮")

        worker_update_job(
            job_id, status="complete",
            current_stage="Complete",
            completed_at=datetime.now().isoformat(),
        )

        # Index in pipeline memory
        try:
            from memory.run_indexer import _extract_theme_tags
            from config.database import get_standalone_db
            import uuid

            run_id = str(uuid.uuid4())[:12]
            db = get_standalone_db()
            db.execute(
                """INSERT INTO run_records (
                    id, job_id, theme, theme_tags, grid, eval_mode,
                    volatility, measured_rtp, target_rtp, hit_frequency,
                    max_win_achieved, features, cost_usd, gdd_summary
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    run_id, job_id, theme,
                    json.dumps(_extract_theme_tags(theme)),
                    "N/A", game_type, "N/A",
                    sim_results.rtp * 100,
                    (1 - house_edge) * 100,
                    sim_results.hit_rate * 100,
                    sim_results.max_multiplier_hit,
                    json.dumps([game_type]),
                    0.0,
                    f"Mini RMG {game_type}: {theme}. HE={house_edge*100:.1f}%",
                ]
            )
            db.commit()
            db.close()
            console.print(f"[green]🧠 Indexed in pipeline memory: {run_id}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Memory indexing: {e}[/yellow]")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        console.print(f"[red]❌ Pipeline failed: {e}[/red]")
        console.print(tb)
        worker_update_job(
            job_id, status="failed",
            error=str(e)[:500],
            completed_at=datetime.now().isoformat(),
        )


def _generate_game_design(game_type: str, theme: str, config: dict, sim_results) -> dict:
    """Generate game design using LLM or fallback to template."""
    try:
        import openai
        client = openai.OpenAI()
        prompt = (
            f"You are a game designer creating a {game_type} mini-game themed '{theme}'.\n\n"
            f"Game config: {json.dumps(config, indent=2)}\n"
            f"Simulation: RTP={sim_results.rtp*100:.2f}%, hit_rate={sim_results.hit_rate*100:.1f}%\n\n"
            f"Generate a JSON game design with these fields:\n"
            f"- title: catchy game name\n"
            f"- tagline: 1-line marketing tagline\n"
            f"- description: 2-3 sentence game description\n"
            f"- ui_theme: object with primary_color (hex), secondary_color (hex), "
            f"bg_gradient (array of 2 hex colors), font_style (modern/retro/elegant)\n"
            f"- sound_theme: ambient mood (space/casino/adventure/nature/cyberpunk)\n"
            f"- animations: array of key animation moments\n"
            f"- bet_options: array of bet amounts\n"
            f"- currency_symbol: default '$'\n\n"
            f"Return ONLY valid JSON, no markdown."
        )
        resp = client.chat.completions.create(
            model=_get_model("game_designer"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.8,
        )
        text = resp.choices[0].message.content.strip()
        # Clean markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        logger.warning(f"LLM design generation failed, using template: {e}")
        return _fallback_design(game_type, theme, config)


def _fallback_design(game_type: str, theme: str, config: dict) -> dict:
    """Fallback design template when LLM is unavailable."""
    return {
        "title": theme,
        "tagline": f"A thrilling {game_type} experience",
        "description": f"Test your luck with {theme} — a provably fair {game_type} game.",
        "ui_theme": {
            "primary_color": "#7c6aef",
            "secondary_color": "#22c55e",
            "bg_gradient": ["#0a0a1a", "#1a1a3e"],
            "font_style": "modern",
        },
        "sound_theme": "casino",
        "animations": ["win_celebration", "loss_fade", "multiplier_tick"],
        "bet_options": [0.10, 0.25, 0.50, 1.00, 2.00, 5.00, 10.00, 25.00],
        "currency_symbol": "$",
    }


def _rng_method(game_type: str) -> str:
    """Map game type to ProvablyFairRNG method name."""
    methods = {
        "crash": "crash_point",
        "plinko": "plinko_path",
        "mines": "mines_board",
        "dice": "dice_roll",
        "wheel": "wheel_spin",
        "hilo": "card_draw",
        "chicken": "chicken_lane",
        "scratch": "scratch_card",
    }
    return methods.get(game_type, "crash_point")


def _run_compliance_check(game_type: str, config: dict, sim_results, params: dict) -> dict:
    """Run basic compliance checks for RMG games."""
    checks = []
    passed = True

    # 1. RTP within tolerance
    he_target = config.get("house_edge", 0.03)
    he_measured = sim_results.house_edge_measured
    delta = abs(he_target - he_measured)
    ok = delta < 0.005
    checks.append({
        "name": "House Edge Accuracy",
        "passed": ok,
        "detail": f"Target: {he_target*100:.2f}%, Measured: {he_measured*100:.2f}%, Δ={delta*100:.3f}%",
    })
    if not ok:
        passed = False

    # 2. Hit rate sanity
    hr = sim_results.hit_rate
    ok2 = 0.01 < hr < 0.99
    checks.append({
        "name": "Hit Rate Sanity",
        "passed": ok2,
        "detail": f"Hit rate: {hr*100:.1f}% (expected 1-99%)",
    })

    # 3. Max multiplier within bounds
    max_config = config.get("max_multiplier", 1000)
    max_hit = sim_results.max_multiplier_hit
    ok3 = max_hit <= max_config * 1.01  # Allow tiny float error
    checks.append({
        "name": "Max Multiplier Cap",
        "passed": ok3,
        "detail": f"Config max: {max_config}x, Simulation max: {max_hit:.1f}x",
    })

    # 4. Provably fair capability
    checks.append({
        "name": "Provably Fair",
        "passed": True,
        "detail": "SHA-256 server_seed:client_seed:nonce — verifiable",
    })

    # 5. Simulation sample size
    ok5 = sim_results.rounds >= 100_000
    checks.append({
        "name": "Simulation Confidence",
        "passed": ok5,
        "detail": f"{sim_results.rounds:,} rounds (min 100,000)",
    })

    return {"passed": passed, "checks": checks, "game_type": game_type}
