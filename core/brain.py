"""
NEXUS AI Brain — Local semantic file categorization engine.
No API. No cloud. Runs entirely on your hardware.

Architecture:
  1. TF-IDF vectorizer for semantic content understanding
  2. Rule-based ontology for domain detection (code, legal, finance, science, etc.)
  3. Context memory — learns patterns across sessions
  4. Ollama bridge — if installed, upgrades to full LLM reasoning automatically
"""

import re
import os
import json
import math
import hashlib
import subprocess
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime

# ─── Domain Ontology ────────────────────────────────────────────────────────

DOMAIN_ONTOLOGY = {
    "Software & Code": {
        "keywords": [
            "function", "class", "import", "def ", "return", "variable", "algorithm",
            "database", "api", "server", "client", "debug", "compile", "runtime",
            "array", "loop", "conditional", "exception", "module", "library",
            "git", "commit", "branch", "deploy", "docker", "kubernetes", "linux",
            "python", "javascript", "java", "cpp", "rust", "golang", "typescript",
            "html", "css", "react", "node", "sql", "nosql", "mongodb", "postgresql",
            "http", "rest", "graphql", "oauth", "jwt", "encryption", "hash",
            "test", "unittest", "pytest", "CI/CD", "pipeline", "devops", "agile"
        ],
        "extensions": [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c",
                       ".h", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
                       ".sh", ".bash", ".zsh", ".fish", ".ps1", ".json", ".yaml",
                       ".yml", ".toml", ".ini", ".env", ".dockerfile", ".makefile",
                       ".sql", ".graphql", ".proto", ".html", ".css", ".scss"],
        "subcategories": {
            "Web Development": ["html", "css", "javascript", "react", "vue", "angular", "frontend", "backend", "http"],
            "Data Science": ["pandas", "numpy", "matplotlib", "sklearn", "tensorflow", "pytorch", "jupyter", "notebook", "dataset", "model", "training"],
            "DevOps & Infrastructure": ["docker", "kubernetes", "terraform", "ansible", "ci/cd", "pipeline", "deploy", "nginx", "cloud", "aws", "gcp", "azure"],
            "Mobile Development": ["swift", "kotlin", "flutter", "react native", "android", "ios", "xcode"],
            "Scripts & Automation": ["bash", "shell", "script", "automation", "cron", "task", "batch"],
            "Databases": ["sql", "query", "schema", "table", "index", "migration", "orm"],
        }
    },
    "Finance & Accounting": {
        "keywords": [
            "invoice", "payment", "revenue", "expense", "budget", "profit", "loss",
            "tax", "audit", "balance", "sheet", "income", "cash", "flow", "equity",
            "dividend", "portfolio", "investment", "stock", "bond", "fund", "asset",
            "liability", "depreciation", "amortization", "interest", "loan", "credit",
            "debit", "ledger", "journal", "account", "financial", "statement", "quarter",
            "fiscal", "annual", "report", "forecast", "roi", "kpi", "margin"
        ],
        "extensions": [".xlsx", ".xls", ".csv", ".pdf", ".docx"],
        "subcategories": {
            "Invoices & Receipts": ["invoice", "receipt", "payment", "bill", "charge", "amount due"],
            "Tax Documents": ["tax", "return", "deduction", "refund", "irs", "w-2", "1099", "gst", "vat"],
            "Budgets & Forecasts": ["budget", "forecast", "projection", "estimate", "plan", "target"],
            "Investment & Portfolio": ["stock", "bond", "portfolio", "dividend", "return", "market"],
            "Payroll": ["salary", "payroll", "wage", "compensation", "benefits", "bonus"],
        }
    },
    "Legal & Compliance": {
        "keywords": [
            "agreement", "contract", "clause", "party", "parties", "jurisdiction",
            "liability", "indemnify", "warrant", "covenant", "obligation", "rights",
            "terms", "conditions", "pursuant", "hereby", "whereas", "hereinafter",
            "intellectual property", "copyright", "trademark", "patent", "license",
            "nda", "confidential", "privacy", "gdpr", "compliance", "regulation",
            "law", "legal", "court", "arbitration", "dispute", "litigation"
        ],
        "extensions": [".pdf", ".docx", ".doc"],
        "subcategories": {
            "Contracts & Agreements": ["agreement", "contract", "parties", "clause", "terms"],
            "NDAs & Confidentiality": ["nda", "confidential", "non-disclosure", "proprietary"],
            "Intellectual Property": ["copyright", "trademark", "patent", "license", "ip"],
            "Compliance & Regulations": ["compliance", "gdpr", "regulation", "policy", "procedure"],
        }
    },
    "Academic & Research": {
        "keywords": [
            "abstract", "introduction", "methodology", "conclusion", "references",
            "bibliography", "hypothesis", "experiment", "analysis", "data", "results",
            "figure", "table", "equation", "theorem", "proof", "citation", "journal",
            "paper", "thesis", "dissertation", "research", "study", "survey",
            "literature", "review", "peer", "academic", "university", "scholar",
            "physics", "chemistry", "biology", "mathematics", "statistics", "quantum",
            "neural", "machine learning", "deep learning", "nlp", "computer vision"
        ],
        "extensions": [".pdf", ".docx", ".tex", ".bib"],
        "subcategories": {
            "Research Papers": ["abstract", "methodology", "conclusion", "references", "doi"],
            "Lecture Notes": ["lecture", "notes", "chapter", "topic", "week", "class", "course"],
            "Assignments": ["assignment", "homework", "exercise", "problem", "submit", "due"],
            "Theses & Dissertations": ["thesis", "dissertation", "degree", "university", "supervisor"],
            "Mathematics": ["theorem", "proof", "equation", "calculus", "algebra", "geometry"],
            "Physics & Chemistry": ["physics", "chemistry", "quantum", "molecule", "atom", "reaction"],
            "Computer Science": ["algorithm", "complexity", "graph", "tree", "network", "machine learning"],
            "Biology & Medicine": ["biology", "cell", "gene", "protein", "clinical", "patient", "drug"],
        }
    },
    "Creative & Media": {
        "keywords": [
            "design", "creative", "art", "style", "color", "font", "typography",
            "brand", "logo", "mockup", "wireframe", "prototype", "ux", "ui",
            "story", "character", "plot", "narrative", "script", "screenplay",
            "music", "audio", "sound", "video", "film", "photography", "edit"
        ],
        "extensions": [".psd", ".ai", ".fig", ".sketch", ".svg", ".png", ".jpg",
                       ".jpeg", ".mp4", ".mov", ".mp3", ".wav", ".gif", ".webp"],
        "subcategories": {
            "Design Assets": ["design", "logo", "brand", "color", "font", "ui", "ux"],
            "Writing & Scripts": ["story", "script", "screenplay", "novel", "chapter", "character"],
            "Music & Audio": ["music", "audio", "sound", "beat", "track", "mix"],
            "Video & Film": ["video", "film", "edit", "clip", "footage", "render"],
        }
    },
    "Business & Management": {
        "keywords": [
            "meeting", "agenda", "minutes", "action", "items", "deadline", "milestone",
            "project", "plan", "strategy", "objective", "goal", "kpi", "metric",
            "presentation", "slide", "deck", "proposal", "pitch", "client", "customer",
            "team", "manager", "stakeholder", "deliverable", "scope", "timeline",
            "email", "memo", "newsletter", "announcement", "hr", "onboarding"
        ],
        "extensions": [".pptx", ".docx", ".pdf", ".xlsx"],
        "subcategories": {
            "Presentations & Decks": ["presentation", "slide", "deck", "pitch"],
            "Project Management": ["project", "milestone", "deadline", "sprint", "kanban", "scrum"],
            "Meeting Notes": ["meeting", "agenda", "minutes", "action items", "attendees"],
            "HR & People": ["hr", "employee", "onboarding", "performance", "review", "hiring"],
            "Marketing & Sales": ["marketing", "sales", "campaign", "lead", "conversion", "brand"],
        }
    },
    "Personal": {
        "keywords": [
            "personal", "diary", "journal", "photo", "family", "vacation", "travel",
            "recipe", "health", "fitness", "goal", "habit", "todo", "list",
            "birthday", "anniversary", "holiday", "memory", "letter"
        ],
        "extensions": [".jpg", ".jpeg", ".png", ".pdf", ".docx", ".txt"],
        "subcategories": {
            "Photos & Memories": ["photo", "picture", "image", "family", "vacation", "trip"],
            "Health & Fitness": ["health", "fitness", "workout", "diet", "medical", "prescription"],
            "Travel": ["travel", "trip", "hotel", "flight", "itinerary", "passport", "visa"],
            "Recipes & Food": ["recipe", "ingredient", "cook", "bake", "food", "meal"],
        }
    },
    "Configuration & Data": {
        "keywords": [
            "config", "configuration", "settings", "environment", "variable",
            "schema", "data", "json", "xml", "csv", "log", "backup"
        ],
        "extensions": [".json", ".xml", ".csv", ".yaml", ".yml", ".toml", ".ini",
                       ".cfg", ".conf", ".log", ".bak", ".db", ".sqlite"],
        "subcategories": {
            "Config Files": ["config", "settings", "environment", "variable"],
            "Data Files": ["data", "dataset", "schema", "record"],
            "Logs": ["log", "error", "warning", "trace", "debug"],
        }
    }
}

# Exact system root paths that should NEVER be the target directory
PROTECTED_EXACT = {
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc",
    "/root", "/run", "/sbin", "/srv", "/sys", "/tmp", "/usr", "/var",
    "/System", "/Library", "/Applications", "/private",
    "C:\\", "C:\\Windows", "C:\\System32", "C:\\Program Files",
    "C:\\Program Files (x86)",
}

# Substrings that must never appear anywhere in the path
PROTECTED_FRAGMENTS = {
    ".git", "node_modules", "__pycache__", "site-packages",
    ".npm", ".cargo", ".rustup",
}

# Top-level directory names that are dangerous when they appear as root
DANGEROUS_ROOTS = {
    "bin", "sbin", "lib", "lib64", "usr", "etc",
    "sys", "proc", "dev", "boot",
}


def is_protected_path(path: str) -> bool:
    """
    Return True only if path IS a system root or contains forbidden fragments.
    Subdirectories of /tmp, ~/Downloads, etc. are allowed — only the bare
    system roots and paths containing e.g. node_modules are blocked.
    """
    raw = str(path).replace("\\", "/")

    # Explicit Windows system root checks (work cross-platform)
    # Block any drive root (e.g., C:/, D:\)
    if re.match(r'^[a-z]:/?$', raw.lower()):
        return True

    win_blocked = {
        "c:/windows", "c:/windows/system32",
        "c:/program files", "c:/program files (x86)",
    }
    if raw.lower().rstrip("/") in win_blocked or raw.lower() in win_blocked:
        return True
    # Block any Windows system subpath
    for blocked in ("c:/windows/", "c:/program files/", "c:/program files (x86)/"):
        if raw.lower().startswith(blocked):
            return True

    resolved = str(Path(path).resolve())

    # Block exact POSIX system roots
    if resolved in PROTECTED_EXACT:
        return True

    # Block paths that contain forbidden fragments as a full path component
    parts = Path(resolved).parts
    for part in parts:
        if part in PROTECTED_FRAGMENTS:
            return True

    # Block paths whose second component is a dangerous Linux root dir
    # e.g. /bin, /usr — but NOT /tmp/myfiles (tmp not in DANGEROUS_ROOTS)
    if len(parts) >= 2 and parts[0] == "/" and parts[1] in DANGEROUS_ROOTS:
        return True

    return False


def simple_tfidf(text: str, corpus_stats: dict = None) -> dict:
    """Compute TF scores for terms in text (lightweight, no sklearn needed at runtime)."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    if not words:
        return {}
    tf = Counter(words)
    total = len(words)
    return {w: c / total for w, c in tf.most_common(100)}


def cosine_similarity_dicts(a: dict, b: dict) -> float:
    """Cosine similarity between two TF dicts."""
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v**2 for v in a.values()))
    mag_b = math.sqrt(sum(v**2 for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class NexusBrain:
    """
    The core AI reasoning engine for NEXUS.
    Combines rule-based ontology matching with semantic similarity
    and optional Ollama LLM for enhanced reasoning.
    """

    def __init__(self, memory_path: str = None):
        self.memory_path = memory_path or os.path.expanduser("~/.nexus/memory.json")
        self.memory = self._load_memory()
        self.ollama_available = self._check_ollama()
        self._build_domain_vectors()

    def _check_ollama(self) -> bool:
        """Check if Ollama is installed and running locally."""
        try:
            startupinfo = None
            if os.name == 'nt':
                STARTUPINFO = getattr(subprocess, 'STARTUPINFO', None)
                if STARTUPINFO:
                    startupinfo = STARTUPINFO()
                    startupinfo.dwFlags |= getattr(subprocess, 'STARTF_USESHOWWINDOW', 0)
                
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, timeout=3,
                startupinfo=startupinfo
            )
            return result.returncode == 0
        except Exception:
            return False

    def _build_domain_vectors(self):
        """Pre-compute TF vectors for each domain's keyword set."""
        self.domain_vectors = {}
        for domain, data in DOMAIN_ONTOLOGY.items():
            text = " ".join(data["keywords"] * 3)  # weight keywords heavily
            self.domain_vectors[domain] = simple_tfidf(text)

    def _load_memory(self) -> dict:
        """Load past organization decisions from disk."""
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "decisions": [],
            "corrections": [],
            "directory_profiles": {},
            "learned_patterns": {}
        }

    def save_memory(self):
        """Persist memory to disk."""
        with open(self.memory_path, "w") as f:
            json.dump(self.memory, f, indent=2, default=str)

    def record_decision(self, file_path: str, destination: str, category: str, reasoning: str):
        """Record an organization decision for future learning."""
        self.memory["decisions"].append({
            "file": file_path,
            "destination": destination,
            "category": category,
            "reasoning": reasoning,
            "timestamp": datetime.now().isoformat()
        })
        # Keep last 1000 decisions
        self.memory["decisions"] = self.memory["decisions"][-1000:]
        self.save_memory()

    def record_correction(self, file_path: str, wrong_dest: str, correct_dest: str):
        """Learn from user corrections."""
        self.memory["corrections"].append({
            "file": file_path,
            "wrong": wrong_dest,
            "correct": correct_dest,
            "timestamp": datetime.now().isoformat()
        })
        self.save_memory()

    def analyze_content(self, content: str, filename: str, extension: str) -> dict:
        """
        Main analysis method. Returns category, subcategory, confidence, and reasoning.
        Falls back gracefully: Ollama → Local semantic → Rule-based → Extension-based
        """
        content_lower = content.lower()
        filename_lower = filename.lower()

        # 1. Try Ollama if available (best quality)
        if self.ollama_available:
            result = self._ollama_reason(content, filename)
            if result:
                return result

        # 2. Local semantic analysis
        return self._local_reason(content_lower, filename_lower, extension)

    def _ollama_reason(self, content: str, filename: str) -> dict | None:
        """Use local Ollama LLM for intelligent categorization."""
        # Truncate content for context window
        snippet = content[:2000].strip()
        domain_list = "\n".join(f"- {d}" for d in DOMAIN_ONTOLOGY.keys())
        
        prompt = f"""You are a file organization AI. Analyze this file and categorize it.

Filename: {filename}
Content preview:
{snippet}

Available top-level categories:
{domain_list}

Respond in this exact JSON format (no other text):
{{
  "category": "<one of the categories above>",
  "subcategory": "<specific subcategory>",
  "suggested_folder": "<folder name using / for nesting, e.g. Academic & Research/Computer Science>",
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 sentence explanation of why>"
}}"""

        try:
            startupinfo = None
            if os.name == 'nt':
                STARTUPINFO = getattr(subprocess, 'STARTUPINFO', None)
                if STARTUPINFO:
                    startupinfo = STARTUPINFO()
                    startupinfo.dwFlags |= getattr(subprocess, 'STARTF_USESHOWWINDOW', 0)
                
            result = subprocess.run(
                ["ollama", "run", "mistral", prompt],
                capture_output=True, text=True, timeout=30,
                startupinfo=startupinfo,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode == 0:
                # Extract JSON from output
                match = re.search(r'\{.*\}', result.stdout, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    data["engine"] = "ollama"
                    return data
        except Exception:
            pass
        return None

    def _local_reason(self, content: str, filename: str, extension: str) -> dict:
        """
        Local semantic + rule-based reasoning.
        Steps:
          1. Score each domain by keyword overlap + cosine similarity
          2. Detect subcategory within winning domain
          3. Apply extension hints
          4. Build human-readable reasoning
        """
        content_vec = simple_tfidf(content)
        
        domain_scores = {}
        domain_keyword_hits = {}

        for domain, data in DOMAIN_ONTOLOGY.items():
            # Cosine similarity with domain vector
            cos_score = cosine_similarity_dicts(content_vec, self.domain_vectors[domain])
            
            # Direct keyword counting (fast, high signal)
            hits = []
            for kw in data["keywords"]:
                if kw.lower() in content or kw.lower() in filename:
                    hits.append(kw)
            keyword_score = min(len(hits) / 10.0, 1.0)
            
            # Extension bonus
            ext_bonus = 0.15 if extension.lower() in [e.lower() for e in data.get("extensions", [])] else 0.0
            
            # Combined score
            domain_scores[domain] = cos_score * 0.5 + keyword_score * 0.4 + ext_bonus
            domain_keyword_hits[domain] = hits

        # Sort domains by score
        ranked = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        best_domain, best_score = ranked[0]

        # Detect subcategory
        subcategory = self._detect_subcategory(best_domain, content, filename)

        # Build folder path
        if subcategory:
            folder = f"{best_domain}/{subcategory}"
        else:
            folder = best_domain

        # Build reasoning
        top_hits = domain_keyword_hits[best_domain][:5]
        confidence = min(best_score * 1.5, 0.95) if best_score > 0.05 else 0.3

        if top_hits:
            reasoning = (
                f"Detected '{best_domain}' domain based on keywords: "
                f"{', '.join(top_hits[:4])}."
            )
        else:
            reasoning = f"Matched '{best_domain}' via file type ({extension}) and content structure."

        if subcategory:
            reasoning += f" Content style indicates '{subcategory}' subcategory."

        # Low confidence = bin
        if confidence < 0.2 and extension not in [".py", ".js", ".pdf", ".docx", ".xlsx"]:
            return {
                "category": "Uncategorized",
                "subcategory": None,
                "suggested_folder": "_bin",
                "confidence": confidence,
                "reasoning": f"Could not confidently categorize (score: {best_score:.2f}). Moving to bin.",
                "engine": "local"
            }

        return {
            "category": best_domain,
            "subcategory": subcategory,
            "suggested_folder": folder,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
            "engine": "local"
        }

    def _detect_subcategory(self, domain: str, content: str, filename: str) -> str | None:
        """Find the best subcategory within a domain."""
        subcats = DOMAIN_ONTOLOGY[domain].get("subcategories", {})
        if not subcats:
            return None

        scores = {}
        for subcat, keywords in subcats.items():
            hits = sum(1 for kw in keywords if kw.lower() in content or kw.lower() in filename)
            scores[subcat] = hits

        best = max(scores, key=scores.get)
        if scores[best] >= 1:
            return best
        return None

    def suggest_directory_structure(self, scan_results: list) -> dict:
        """
        Given a list of categorized files, suggest an optimal directory tree.
        Groups files and avoids creating near-empty folders.
        """
        category_counts = Counter()
        subcategory_counts = Counter()

        for r in scan_results:
            if r.get("suggested_folder") != "_bin":
                cat = r.get("category", "Uncategorized")
                sub = r.get("subcategory")
                category_counts[cat] += 1
                if sub:
                    subcategory_counts[f"{cat}/{sub}"] += 1

        structure = {}
        for cat, count in category_counts.items():
            if count >= 1:  # create folder even for 1 file
                structure[cat] = {
                    "count": count,
                    "subcategories": {}
                }

        for path, count in subcategory_counts.items():
            cat, sub = path.split("/", 1)
            if cat in structure and count >= 1:
                cat_dict = structure[cat]
                if isinstance(cat_dict, dict) and "subcategories" in cat_dict:
                    cat_dict["subcategories"][sub] = count

        return structure

    def get_stats(self) -> dict:
        return {
            "total_decisions": len(self.memory["decisions"]),
            "total_corrections": len(self.memory["corrections"]),
            "ollama_available": self.ollama_available,
            "engine": "ollama" if self.ollama_available else "local-semantic"
        }
