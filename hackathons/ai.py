"""
AI Services for HackFlow Hackathons Module.
Supports direct Gemini API integration (if GEMINI_API_KEY is configured in .env)
with a built-in domain-specific generative engine as zero-config fallback.
"""
import os
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_hackathon_content(title: str, category: str = "", theme_hints: str = ""):
    """
    Generate complete hackathon content (tagline, description, rules, sample milestones)
    based on the title, category, and optional hints.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    if gemini_key:
        try:
            import urllib.request
            prompt = (
                f"You are an expert hackathon organizer. Generate compelling content for a hackathon titled '{title}'. "
                f"Category: '{category}'. Hints: '{theme_hints}'.\n"
                "Respond ONLY with a valid JSON object with the following keys:\n"
                "- 'tagline': A catchy, punchy one-liner (max 15 words)\n"
                "- 'description': 3-4 structured paragraphs detailing the mission, challenge prompt, and expected impact.\n"
                "- 'rules': Clear bullet points covering original code, submission checklist, fairness, and evaluation criteria.\n"
                "- 'suggested_skills': A list of 4-6 recommended skills/technologies (e.g. ['Python', 'Django', 'React', 'OpenAI API']).\n"
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_content)
        except Exception as exc:
            logger.warning("Gemini API call failed, falling back to local generative engine: %s", exc)

    # ── Built-in High-Fidelity Domain Generative Engine ──
    title_lower = title.lower()
    cat_lower = (category or "").lower()
    
    # Detect domain
    if any(k in title_lower or k in cat_lower for k in ["ai", "ia", "data", "ml", "intelligence"]):
        domain = "ai"
    elif any(k in title_lower or k in cat_lower for k in ["cyber", "security", "shield", "hack", "defense"]):
        domain = "cyber"
    elif any(k in title_lower or k in cat_lower for k in ["green", "eco", "climate", "sustainab", "energy", "earth"]):
        domain = "green"
    elif any(k in title_lower or k in cat_lower for k in ["health", "med", "bio", "care"]):
        domain = "health"
    elif any(k in title_lower or k in cat_lower for k in ["web3", "block", "crypto", "defi", "chain"]):
        domain = "web3"
    elif any(k in title_lower or k in cat_lower for k in ["finance", "fintech", "bank", "pay", "trade"]):
        domain = "fintech"
    else:
        domain = "general"

    templates = {
        "ai": {
            "tagline": f"Unleash next-generation intelligent agents and predictive systems at {title}.",
            "description": (
                f"Welcome to {title}! This hackathon brings together visionary developers, data scientists, and product designers "
                "to push the boundaries of Artificial Intelligence and Machine Learning.\n\n"
                "Participants are challenged to build end-to-end applications that solve tangible human problems—from autonomous "
                "workflows and intelligent assistants to computer vision and multimodal reasoning. "
                "Whether you are leveraging foundation models, fine-tuning open-source LLMs, or deploying custom neural networks, "
                "your project must demonstrate both technical depth and real-world applicability.\n\n"
                "Mentors and industry experts will be on-site to guide your team through architecture, data pipelines, and pitch polish."
            ),
            "rules": (
                "1. Original Code: All models, APIs, and interfaces must be developed during the official competition window.\n"
                "2. Open APIs & Libraries: Pre-trained foundation models (OpenAI, Gemini, HuggingFace, Anthropic) and open datasets are permitted provided they are cited.\n"
                "3. Deliverables: Public GitHub repository, interactive video demo or live URL, and architecture pitch deck.\n"
                "4. Evaluation Matrix: Technical Execution (30%), Innovation (25%), Practical Impact (25%), Presentation Quality (20%).\n"
                "5. Fair Play: Strict adherence to academic integrity and respectful collaboration."
            ),
            "suggested_skills": ["Python", "FastAPI", "React", "PyTorch", "LangChain", "PostgreSQL"],
        },
        "cyber": {
            "tagline": f"Fortify digital frontiers and engineer resilient defense systems at {title}.",
            "description": (
                f"{title} is the premier challenge for cybersecurity enthusiasts, system architects, and ethical hackers.\n\n"
                "Our mission: build tools, defenses, and protocols that safeguard critical infrastructure, detect sophisticated threats in real time, "
                "and ensure privacy in an increasingly hostile threat landscape.\n\n"
                "Teams will tackle challenges ranging from automated threat intelligence and vulnerability scanners to zero-trust access controls "
                "and cryptographic protocols."
            ),
            "rules": (
                "1. Ethical Boundary: All penetration testing tools and vulnerability scanners must run exclusively within sandbox environments provided.\n"
                "2. Original Implementation: Exploits or defensive scripts must be written during the competition.\n"
                "3. Deliverables: Source code repo with Dockerfile/deployment instructions, threat model analysis, and live proof of concept.\n"
                "4. Evaluation Rubric: Technical Sophistication (35%), Defense Impact (25%), Usability (20%), Pitch (20%)."
            ),
            "suggested_skills": ["Python", "Rust", "Linux/Bash", "Docker", "Network Analysis", "Cryptography"],
        },
        "green": {
            "tagline": f"Build sustainable technology and carbon-intelligent solutions at {title}.",
            "description": (
                f"{title} invites forward-thinking creators to apply technology toward our planet's most urgent challenges.\n\n"
                "Teams are challenged to build digital solutions that accelerate renewable energy adoption, optimize urban resource consumption, "
                "monitor biodiversity, or empower consumers to track and reduce their carbon footprint.\n\n"
                "Merge hardware sensors, satellite imagery, cloud microservices, and mobile interfaces into scalable climate solutions."
            ),
            "rules": (
                "1. Sustainability Focus: Solutions must address a quantifiable ecological, agricultural, or energy efficiency challenge.\n"
                "2. Open Datasets: Public climate datasets (Copernicus, NASA, NOAA, OpenWeather) are encouraged.\n"
                "3. Deliverables: Working code repository, carbon impact estimation methodology, and demo video.\n"
                "4. Scoring Criteria: Environmental Impact (30%), Technical Feasibility (30%), Innovation (20%), User Experience (20%)."
            ),
            "suggested_skills": ["Python", "GIS/Spatial Data", "TypeScript", "Next.js", "IoT/Sensors", "TailwindCSS"],
        },
        "general": {
            "tagline": f"48 hours of rapid prototyping, collaboration and breakthrough innovation at {title}.",
            "description": (
                f"{title} is an open-canvas hackathon designed to empower builders to turn bold ideas into production-ready prototypes.\n\n"
                "Over the course of this event, multi-disciplinary teams will sprint from problem definition to user research, "
                "high-velocity coding, and high-impact pitching before a jury of industry leaders and investors.\n\n"
                "Build for the web, mobile, hardware, or cloud. Focus on delighting users, solving real friction points, and shipping clean code."
            ),
            "rules": (
                "1. Fresh Repos: All code must be pushed to a fresh repository created at the official kickoff.\n"
                "2. Team Formation: Permitted team sizes must strictly adhere to the event guidelines.\n"
                "3. Deliverables: Public repository, working deployment or live recording, and slide deck.\n"
                "4. Judging Pillars: Innovation (25%), Technical Execution (30%), Market Potential (25%), Demo Quality (20%).\n"
                "5. Code of Conduct: Mutual respect, zero tolerance for harassment, and inclusive team spirit."
            ),
            "suggested_skills": ["Python", "Django", "JavaScript", "React", "PostgreSQL", "Docker"],
        }
    }

    selected = templates.get(domain, templates["general"])
    return selected


def generate_project_ideas(hackathon_title: str, category: str, description: str):
    """
    Generate 3-4 creative project ideas tailored for participants of this hackathon.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            import urllib.request
            prompt = (
                f"You are a hackathon mentor. Suggest 3 innovative project ideas for participants in '{hackathon_title}' "
                f"(Category: '{category}'). Description snippet: '{description[:300]}'.\n"
                "Respond ONLY with a valid JSON array of 3 objects, each having:\n"
                "- 'title': Creative project name\n"
                "- 'problem': The specific problem it solves (2 sentences)\n"
                "- 'solution': How the application solves it (2 sentences)\n"
                "- 'tech_stack': List of 3-4 technologies/frameworks\n"
                "- 'difficulty': 'Beginner', 'Intermediate', or 'Advanced'\n"
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_content)
        except Exception as exc:
            logger.warning("Gemini project idea generation failed, using local ideas: %s", exc)

    # Built-in generator
    t_lower = (hackathon_title + " " + category).lower()
    if "cyber" in t_lower or "security" in t_lower:
        return [
            {
                "title": "SentinelFlow — Automated Zero-Day Threat Detector",
                "problem": "SOC teams are flooded with thousands of low-level alerts daily, missing critical intrusion anomalies.",
                "solution": "An eBPF-powered real-time network anomaly watcher that clusters telemetry data and detects zero-day lateral movements.",
                "tech_stack": ["Python", "FastAPI", "eBPF", "Docker", "ELK"],
                "difficulty": "Advanced",
            },
            {
                "title": "PhishShield AI — Real-time Email & QR Code Verifier",
                "problem": "Modern social engineering exploits dynamic phishing landing pages and deceptive QR codes (quishing).",
                "solution": "A browser extension that previews embedded URLs in a cloud sandbox and performs optical character analysis.",
                "tech_stack": ["TypeScript", "Chrome Extensions API", "Python", "Tesseract OCR"],
                "difficulty": "Intermediate",
            },
            {
                "title": "VaultGuard — Ephemeral Secret Sharing for Remote Teams",
                "problem": "Developers frequently paste sensitive API keys and tokens into unencrypted chat channels.",
                "solution": "Zero-knowledge end-to-end encrypted self-destructing secrets with biometric mobile approval.",
                "tech_stack": ["Web Crypto API", "Django", "TailwindCSS", "PostgreSQL"],
                "difficulty": "Beginner",
            },
        ]
    elif "ai" in t_lower or "data" in t_lower:
        return [
            {
                "title": "DocuPulse AI — Multimodal Research Paper Synthesizer",
                "problem": "Researchers spend dozens of hours skimming dense PDFs to find contradictory experimental findings.",
                "solution": "An agentic RAG system that ingests scientific papers, cross-references claims, and generates visual knowledge graphs.",
                "tech_stack": ["Python", "LangChain", "ChromaDB", "FastAPI", "React Flow"],
                "difficulty": "Advanced",
            },
            {
                "title": "CodeMentor Live — Voice-guided Pair Programming Agent",
                "problem": "Junior engineers struggle when debugging cryptic terminal errors without access to a senior mentor.",
                "solution": "A lightweight desktop audio assistant that listens to speech, inspects terminal logs, and explains bugs in plain terms.",
                "tech_stack": ["Python", "WebSockets", "Whisper API", "Electron / React"],
                "difficulty": "Intermediate",
            },
            {
                "title": "HealthSnap — Personalized Nutrition & Allergy Scanner",
                "problem": "Consumers with complex dietary restrictions struggle to parse ambiguous ingredient labels on food products.",
                "solution": "A mobile web camera scanner that checks food barcodes or nutrition labels against personalized allergy profiles.",
                "tech_stack": ["Django", "OpenFoodFacts API", "TailwindCSS", "Alpine.js"],
                "difficulty": "Beginner",
            },
        ]
    else:
        return [
            {
                "title": "TeamSync — Dynamic Skill-Matched Hackathon Builder",
                "problem": "Solitary participants struggle to find complementary teammates, resulting in unbalanced squads.",
                "solution": "An algorithmic matching system that evaluates participant strengths and optimizes team synergy scores.",
                "tech_stack": ["Python", "Django", "HTMX", "PostgreSQL"],
                "difficulty": "Intermediate",
            },
            {
                "title": "EcoRoute — Carbon-Optimized Urban Delivery Scheduler",
                "problem": "Last-mile delivery vehicles produce disproportionate urban emissions due to inefficient routing.",
                "solution": "A route optimization engine that factors in vehicle propulsion type, topography, and live congestion.",
                "tech_stack": ["Python", "OSRM API", "Leaflet.js", "FastAPI"],
                "difficulty": "Advanced",
            },
            {
                "title": "CampusHub — Micro-Mentorship & Office Hours Booking",
                "problem": "Students lack direct access to alumni and industry professionals for fast technical guidance.",
                "solution": "A micro-mentorship platform with real-time video slots, calendar syncing, and review portfolios.",
                "tech_stack": ["Django", "TailwindCSS", "WebRTC", "PostgreSQL"],
                "difficulty": "Beginner",
            },
        ]


def calculate_team_match_score(student_skills: list, candidate_skills: list) -> dict:
    """
    Computes a smart complementarity and compatibility score between two participants.
    High score when skills complement each other (e.g. backend + frontend + design).
    """
    s1 = set(s.strip().lower() for s in student_skills if s.strip())
    s2 = set(s.strip().lower() for s in candidate_skills if s.strip())
    
    if not s1 or not s2:
        return {"score": 50, "overlap": [], "complementary": list(s2), "synergy": "Basic Match"}

    overlap = list(s1.intersection(s2))
    complementary = list(s2.difference(s1))

    # Categories
    categories = {
        "frontend": {"react", "vue", "angular", "html", "css", "tailwind", "ui/ux", "frontend", "next.js", "figma"},
        "backend": {"python", "django", "fastapi", "flask", "node", "express", "sql", "postgresql", "backend", "java", "go"},
        "ai_data": {"ai", "machine learning", "deep learning", "pytorch", "tensorflow", "data science", "nlp", "computer vision"},
        "mobile_devops": {"flutter", "react native", "swift", "kotlin", "docker", "kubernetes", "aws", "devops", "cloud"},
        "security": {"cybersecurity", "security", "cryptography", "penetration testing", "ethical hacking"}
    }

    def get_user_cats(skills):
        user_cats = set()
        for cat, cat_skills in categories.items():
            if any(s in cat_skills for s in skills):
                user_cats.add(cat)
        return user_cats

    c1 = get_user_cats(s1)
    c2 = get_user_cats(s2)

    cat_diff = c2.difference(c1)
    
    # Base calculation: complementarity adds 20 points per distinct domain, overlap adds 10 points
    score = 45 + (len(cat_diff) * 18) + (min(len(overlap), 2) * 8) + (min(len(complementary), 3) * 4)
    score = min(98, max(50, score))

    if score >= 85:
        synergy = "🔥 Highly Complementary (Dream Team)"
    elif score >= 70:
        synergy = "✨ Strong Balance (Great Synergy)"
    else:
        synergy = "👍 Good Match"

    return {
        "score": score,
        "overlap": overlap,
        "complementary": complementary,
        "synergy": synergy
    }
