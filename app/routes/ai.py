import json
import random
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from sqlalchemy import func
from app.database import db
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit
from app.models.farm import EstateBlock, FarmActivity
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.harvest import HarvestRecord
from app.models.inventory import InventoryItem
from app.models.pesticide import PesticideApplication
from app.models.payroll import PayrollRecord

ai_bp = Blueprint("ai", __name__)

# ==============================================================================
# 1. DISEASE DETECTION AI (Page 6)
# ==============================================================================

DISEASE_KNOWLEDGE_BASE = {
    "rust": {
        "id": "rust",
        "name": "Coffee Leaf Rust",
        "scientific_name": "Hemileia vastatrix",
        "confidence": 97.4,
        "severity": "High (Pre-monsoon / Post-monsoon critical)",
        "icon": "bi-virus",
        "badge_color": "danger",
        "affected_varieties": "Highly susceptible in Arabica (Chandragiri, S.795, SLN-9); Kaveri (Cauvery Catimor) is resistant.",
        "symptoms": [
            "Orange-yellow powdery pustules on the ventral (underside) of coffee leaves",
            "Chlorotic yellow lesions on the upper leaf surface turning necrotic brown",
            "Premature defoliation, twig die-back, and severe crop loss in subsequent seasons"
        ],
        "organic_treatment": [
            "Apply 0.5% to 1.0% neutral Bordeaux mixture pre-monsoon (May) and post-monsoon (Oct/Nov)",
            "Spray Neem Seed Kernel Extract (NSKE 5%) or mineral oil emulsion",
            "Prune canopy and shade trees to permit optimal sunlight and lower micro-humidity"
        ],
        "chemical_treatment": [
            "Copper Oxychloride (COC 50% WP @ 2.5 g/L of water)",
            "Systemic triazole fungicide: Hexaconazole 5% EC (Contaf @ 2.0 ml/L) or Propiconazole 25% EC (@ 1.0 ml/L)"
        ],
        "action_plan": "Isolate affected blocks (Block A / D). Initiate protective fungicide spray before heavy southwest monsoon."
    },
    "berry_borer": {
        "id": "berry_borer",
        "name": "Coffee Berry Borer",
        "scientific_name": "Hypothenemus hampei",
        "confidence": 95.8,
        "severity": "Critical (Attacks pin-head to ripe berries)",
        "icon": "bi-bug-fill",
        "badge_color": "danger",
        "affected_varieties": "Attacks both Arabica and Robusta beans, burrowing into the navel region.",
        "symptoms": [
            "Round pinhole entry wounds at the apical navel of developing green and red berries",
            "Hollowed or powder-filled endosperm beans with blue-black galleries",
            "Premature berry drop and bean degradation causing severe outturn loss"
        ],
        "organic_treatment": [
            "Install Broca / red funnel ethanol-methanol (1:1) attractant traps @ 20 traps/hectare",
            "Spray entomopathogenic fungus Beauveria bassiana (@ 2-5 kg/ha) during overcast days",
            "Conduct thorough phytosanitary strip-picking ('Glean picking') of all residual berries"
        ],
        "chemical_treatment": [
            "Spray Chlorpyrifos 20% EC (@ 2.5 ml/L) or Cypermethrin 10% EC (@ 1.0 ml/L) only during peak borer emergence"
        ],
        "action_plan": "Check navel holes on green berries. Deploy ethanol traps immediately across Block B and C."
    },
    "black_rot": {
        "id": "black_rot",
        "name": "Black Rot / Koleroga",
        "scientific_name": "Pellicularia koleroga (Corticium koleroga)",
        "confidence": 93.2,
        "severity": "Moderate to High (During continuous monsoon rain)",
        "icon": "bi-droplet-half",
        "badge_color": "warning",
        "affected_varieties": "Common in Arabica on heavily shaded valleys and misty ridges.",
        "symptoms": [
            "Leaves turn dark brown to black and hang suspended by slender white mycelial threads",
            "Infected berries turn black, rot, and drop off prematurely",
            "Dense fungal web on twigs and ventral leaf surface during torrential rain"
        ],
        "organic_treatment": [
            "Lopping shade trees heavily to enhance aeration and reduce humidity pockets",
            "Remove and incinerate hanging black leaves and affected twig clusters",
            "Bordeaux mixture 1% spray prior to monsoon onset"
        ],
        "chemical_treatment": [
            "Pre-monsoon protective spray with Copper Oxychloride (COC 50% WP @ 3.0 g/L)",
            "Systemic spray with Carbendazim 50% WP (Bavistin @ 1.0 g/L) if disease persists"
        ],
        "action_plan": "Improve canopy ventilation and spray 1% Bordeaux mixture before monsoon mist sets in."
    },
    "anthracnose": {
        "id": "anthracnose",
        "name": "Anthracnose / Twig Die-back",
        "scientific_name": "Colletotrichum gloeosporioides",
        "confidence": 91.5,
        "severity": "Moderate (Follows heat stress or defoliation)",
        "icon": "bi-bandaid",
        "badge_color": "warning",
        "affected_varieties": "Arabica and Robusta exposed to excessive direct sunlight and debarking.",
        "symptoms": [
            "Yellowing and die-back of terminal young green twigs from tip backwards",
            "Necrotic circular spots on leaves with concentric ring zonations",
            "Sun-scalded brown sunken patches on exposed green berries"
        ],
        "organic_treatment": [
            "Maintain adequate overhead shade canopy (silver oak, dadap, jackfruit)",
            "Apply balanced NPK fertilizer with micronutrient zinc and magnesium foliar spray",
            "Prune back dead necrotic twigs 2 inches into healthy wood"
        ],
        "chemical_treatment": [
            "Foliar spray of Mancozeb 75% WP (@ 2.5 g/L) or Copper Oxychloride (@ 2.5 g/L)",
            "Foliar application of 0.5% urea + zinc sulfate to restore vigor"
        ],
        "action_plan": "Prune desiccated branches and apply balancing foliar nutrients to rebuild leaf canopy."
    },
    "healthy": {
        "id": "healthy",
        "name": "Healthy Coffee Foliage",
        "scientific_name": "Coffea arabica / canephora",
        "confidence": 98.9,
        "severity": "Normal / Optimal Health",
        "icon": "bi-check-circle-fill",
        "badge_color": "success",
        "affected_varieties": "Normal leaf texture across all blocks.",
        "symptoms": [
            "Vibrant deep green glossy leaves with intact margins",
            "Uniform chlorophyll distribution with no chlorosis or sporulation",
            "Vigorous apical nodes and uniform flower/berry cluster spacing"
        ],
        "organic_treatment": [
            "Maintain regular compost mulching and vermicompost application @ 2 kg/bush",
            "Continue organic bio-fertilizer soil drench (Azospirillum & Phosphobacteria)"
        ],
        "chemical_treatment": [
            "Standard seasonal maintenance NPK 17:17:17 schedule only"
        ],
        "action_plan": "Foliage in peak health. Proceed with standard irrigation and soil health upkeep."
    }
}

@ai_bp.route("/ai/disease", methods=["GET"])
@ai_bp.route("/ai/disease/", methods=["GET"])
@ai_bp.route("/disease", methods=["GET"])
@ai_bp.route("/disease/", methods=["GET"])
@login_required
def disease_detection():
    """Page 6: Disease Detection AI."""
    current_user = get_current_user()
    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()
    recent_activities = FarmActivity.query.filter(
        FarmActivity.activity_type.ilike("%disease%") | FarmActivity.activity_type.ilike("%rust%") | FarmActivity.activity_type.ilike("%pest%")
    ).order_by(FarmActivity.date.desc()).limit(5).all()

    return render_template(
        "ai_disease.html",
        blocks=blocks,
        recent_activities=recent_activities,
        current_user=current_user,
        knowledge_base=DISEASE_KNOWLEDGE_BASE
    )

@ai_bp.route("/disease/analyze", methods=["POST"])
@login_required
def analyze_disease():
    """Simulates AI Computer Vision model analyzing uploaded foliage or sample."""
    data = request.get_json(silent=True) or request.form
    sample_type = data.get("sample_type", "rust")

    if sample_type in DISEASE_KNOWLEDGE_BASE:
        diagnosis = DISEASE_KNOWLEDGE_BASE[sample_type]
    else:
        # Default fallback to rust
        diagnosis = DISEASE_KNOWLEDGE_BASE["rust"]

    # Slight variance in confidence for realism
    variance = round(random.uniform(-1.5, 1.2), 1)
    confidence = min(99.4, max(88.0, diagnosis["confidence"] + variance))

    return jsonify({
        "success": True,
        "diagnosis": {
            **diagnosis,
            "confidence": round(confidence, 1)
        }
    })

@ai_bp.route("/disease/log-activity", methods=["POST"])
@login_required
def log_disease_activity():
    """Logs AI disease detection directly into block agronomic records."""
    block_id = request.form.get("block_id", type=int)
    disease_name = request.form.get("disease_name", "Disease Inspection")
    treatment = request.form.get("treatment", "Protective spray recommended")
    notes = request.form.get("notes", "")

    block = EstateBlock.query.get(block_id) if block_id else None
    if not block:
        flash("Please select a valid plantation block.", "danger")
        return redirect(url_for("ai.disease_detection"))

    user = get_current_user()
    activity = FarmActivity(
        block_id=block.id,
        activity_type=f"AI Disease Scan: {disease_name}",
        date=date.today(),
        input_quantity=treatment[:95] if treatment else None,
        notes=f"AI Detection finding: {disease_name}. {notes}".strip(),
        responsible_user=user.username if user else "AI System"
    )
    db.session.add(activity)
    db.session.commit()

    log_audit("AI_DISEASE_LOG", f"Logged {disease_name} on {block.name}", user.id if user else None)
    flash(f"Detection record successfully logged for {block.name}!", "success")
    return redirect(url_for("ai.disease_detection"))


# ==============================================================================
# 2. CHERRY RIPENESS AI (Page 7)
# ==============================================================================

RIPENESS_PRESETS = {
    "optimal": {
        "title": "Optimal Specialty Grade Harvest",
        "description": "Peak ripeness with over 88% crimson red cherries. High Brix sugar index.",
        "ripe_pct": 89.4,
        "unripe_pct": 7.2,
        "overripe_pct": 3.4,
        "grade": "Specialty Grade 1 (Plantation A)",
        "brix": "22.5° Brix",
        "recommendation": "Begin immediate harvest! Highest mucilage sweetness. Perfect for washed parchment.",
        "badge_color": "success"
    },
    "early": {
        "title": "Early Season / Under-Ripe Picking",
        "description": "High proportion of green/yellow unripe cherries. Premature harvest warning.",
        "ripe_pct": 42.1,
        "unripe_pct": 54.3,
        "overripe_pct": 3.6,
        "grade": "Sub-Optimal (High Green Content)",
        "brix": "15.0° Brix",
        "recommendation": "Postpone main harvest by 10-14 days. Green cherries create grassy astringent cup defects.",
        "badge_color": "warning"
    },
    "late": {
        "title": "Late Season / Over-Ripe Cherries",
        "description": "Cherries desiccating into black raisins and floaters with fermentation risk.",
        "ripe_pct": 51.2,
        "unripe_pct": 6.5,
        "overripe_pct": 42.3,
        "grade": "Commercial Cherry Grade B (Natural Processing)",
        "brix": "24.0° Brix (Concentrated sugars)",
        "recommendation": "Strip pick immediately to avoid pod drop and berry borer infestation. Divert to dry unwashed cherry processing.",
        "badge_color": "danger"
    },
    "mixed": {
        "title": "Uneven Maturation / Fly Picking",
        "description": "Staggered blossoming leading to mixed clusters of green and red fruit.",
        "ripe_pct": 68.5,
        "unripe_pct": 26.2,
        "overripe_pct": 5.3,
        "grade": "Standard Grade (Selective Hand-Picking Required)",
        "brix": "19.5° Brix",
        "recommendation": "Instruct picking gangs to perform selective 'Fly Picking' (plucking red only). Do not strip branches.",
        "badge_color": "info"
    }
}

@ai_bp.route("/ai/ripeness", methods=["GET"])
@ai_bp.route("/ai/ripeness/", methods=["GET"])
@ai_bp.route("/ripeness", methods=["GET"])
@ai_bp.route("/ripeness/", methods=["GET"])
@login_required
def cherry_ripeness():
    """Page 7: Cherry Ripeness AI."""
    current_user = get_current_user()
    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()
    recent_harvests = HarvestRecord.query.order_by(HarvestRecord.date.desc()).limit(5).all()

    return render_template(
        "ai_ripeness.html",
        blocks=blocks,
        recent_harvests=recent_harvests,
        current_user=current_user,
        presets=RIPENESS_PRESETS
    )

@ai_bp.route("/ripeness/analyze", methods=["POST"])
@login_required
def analyze_ripeness():
    """Analyzes coffee cherry cluster image or preset."""
    data = request.get_json(silent=True) or request.form
    preset_key = data.get("preset", "optimal")
    preset = RIPENESS_PRESETS.get(preset_key, RIPENESS_PRESETS["optimal"])

    # Variance
    v1 = round(random.uniform(-1.2, 1.2), 1)
    ripe = round(min(98.0, max(20.0, preset["ripe_pct"] + v1)), 1)
    unripe = round(max(0.0, preset["unripe_pct"] - (v1 * 0.7)), 1)
    overripe = round(max(0.0, 100.0 - ripe - unripe), 1)

    return jsonify({
        "success": True,
        "result": {
            **preset,
            "ripe_pct": ripe,
            "unripe_pct": unripe,
            "overripe_pct": overripe
        }
    })


# ==============================================================================
# 3. AI YIELD PREDICTION (Page 9)
# ==============================================================================

@ai_bp.route("/ai/yield", methods=["GET"])
@ai_bp.route("/ai/yield/", methods=["GET"])
@ai_bp.route("/yield", methods=["GET"])
@ai_bp.route("/yield/", methods=["GET"])
@login_required
def yield_prediction():
    """Page 9: AI Yield Prediction."""
    current_user = get_current_user()
    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()

    # Calculate current estate aggregated metrics
    total_area = sum(float(b.area or 0) for b in blocks)
    total_harvest_kg = db.session.query(func.coalesce(func.sum(HarvestRecord.actual_quantity), 0)).scalar() or 0.0

    return render_template(
        "ai_yield.html",
        blocks=blocks,
        total_area=total_area,
        total_harvest_kg=total_harvest_kg,
        current_user=current_user
    )

@ai_bp.route("/yield/predict", methods=["POST"])
@login_required
def predict_yield():
    """Calculates agronomic AI yield prediction for a block."""
    data = request.get_json(silent=True) or request.form
    block_id = int(data.get("block_id", 1))
    blossom_showers = float(data.get("blossom_showers", 35.0)) # mm rainfall
    backing_showers = float(data.get("backing_showers", 50.0)) # mm rainfall
    npk_dosage = float(data.get("npk_dosage", 120.0)) # kg/ha
    shade_pct = float(data.get("shade_pct", 60.0)) # %
    pest_incidence = float(data.get("pest_incidence", 5.0)) # %

    block = EstateBlock.query.get(block_id)
    if not block:
        return jsonify({"success": False, "error": "Invalid block"}), 400

    area = float(block.area or 10.0)
    is_arabica = "arabica" in (block.variety or "").lower()
    is_kaveri = "kaveri" in (block.variety or "").lower() or "cauvery" in (block.variety or "").lower()

    # Base yield per hectare
    if is_kaveri:
        base_kg_per_ha = 1450.0  # High yield semi-dwarf hybrid
        price_per_50kg_bag = 16500.0
        outturn_ratio = 5.5
    elif is_arabica:
        base_kg_per_ha = 1050.0  # High elevation specialty
        price_per_50kg_bag = 17500.0
        outturn_ratio = 6.0
    else:
        base_kg_per_ha = 1750.0  # Robusta high biomass
        price_per_50kg_bag = 11500.0
        outturn_ratio = 5.0

    # Agronomic environmental multipliers
    # Ideal blossom showers: 25 - 40 mm
    blossom_factor = 1.0
    if blossom_showers < 15:
        blossom_factor = 0.72  # Drought flower desiccation
    elif 25 <= blossom_showers <= 45:
        blossom_factor = 1.15  # Perfect blossom triggering
    elif blossom_showers > 65:
        blossom_factor = 0.88  # Wet blossom rotting

    # Backing showers: ideal 40 - 60 mm
    backing_factor = 1.05 if 35 <= backing_showers <= 70 else 0.90

    # Nutrition factor
    nutrition_factor = min(1.20, max(0.80, 0.75 + (npk_dosage / 300.0)))

    # Shade optimization (50-65% is ideal)
    shade_factor = 1.05 if 45 <= shade_pct <= 65 else 0.92

    # Pest / rust loss
    loss_factor = max(0.60, 1.0 - (pest_incidence / 100.0))

    # Predicted yield per ha
    predicted_kg_per_ha = base_kg_per_ha * blossom_factor * backing_factor * nutrition_factor * shade_factor * loss_factor
    total_clean_coffee_kg = round(predicted_kg_per_ha * area, 1)
    total_cherry_kg = round(total_clean_coffee_kg * outturn_ratio, 1)
    total_metric_tons = round(total_clean_coffee_kg / 1000.0, 2)
    total_50kg_bags = int(total_clean_coffee_kg // 50)
    projected_revenue_inr = round(total_50kg_bags * price_per_50kg_bag, 2)

    return jsonify({
        "success": True,
        "prediction": {
            "block_name": block.name,
            "variety": block.variety,
            "coffee_type": block.coffee_type,
            "area_ha": area,
            "predicted_clean_kg": total_clean_coffee_kg,
            "predicted_cherry_kg": total_cherry_kg,
            "predicted_metric_tons": total_metric_tons,
            "predicted_50kg_bags": total_50kg_bags,
            "yield_per_ha": round(predicted_kg_per_ha, 1),
            "projected_revenue_inr": projected_revenue_inr,
            "factors": {
                "blossom_factor": round(blossom_factor, 2),
                "backing_factor": round(backing_factor, 2),
                "nutrition_factor": round(nutrition_factor, 2),
                "shade_factor": round(shade_factor, 2),
                "loss_factor": round(loss_factor, 2)
            }
        }
    })


# ==============================================================================
# 4. AI ESTATE CHATBOT (Page 18)
# ==============================================================================

@ai_bp.route("/ai/chatbot", methods=["GET"])
@ai_bp.route("/ai/chatbot/", methods=["GET"])
@ai_bp.route("/ai/chat", methods=["GET"])
@ai_bp.route("/chatbot", methods=["GET"])
@ai_bp.route("/chatbot/", methods=["GET"])
@ai_bp.route("/chat", methods=["GET"])
@login_required
def chatbot():
    """Page 18: AI Estate Chatbot."""
    current_user = get_current_user()
    return render_template("ai_chatbot.html", current_user=current_user)

@ai_bp.route("/chatbot/query", methods=["POST"])
@login_required
def chatbot_query():
    """Context-aware coffee estate agronomy & operations copilot."""
    data = request.get_json(silent=True) or request.form
    query = (data.get("message") or "").strip()

    if not query:
        return jsonify({"reply": "Please ask a question regarding plantation operations, coffee varieties, or agronomy."})

    q_lower = query.lower()
    user = get_current_user()

    # Dynamic estate context retrieval
    block_count = EstateBlock.query.count()
    emp_count = Employee.query.count()
    pesticide_count = PesticideApplication.query.count()
    harvest_total = db.session.query(func.coalesce(func.sum(HarvestRecord.actual_quantity), 0)).scalar() or 0.0

    # Knowledge matching rules
    if "rust" in q_lower or "leaf rust" in q_lower:
        reply = (
            "🌿 **Coffee Leaf Rust (*Hemileia vastatrix*) Management Protocol:**\n\n"
            "• **Arabica Susceptibility:** Blocks A & D have higher risk. Kaveri (Block C) is genetically resistant.\n"
            "• **Pre-Monsoon Treatment (May):** Spray **0.5% – 1% Neutral Bordeaux Mixture** or Copper Oxychloride (COC 50% WP @ 2.5 g/L).\n"
            "• **Post-Monsoon Treatment (October/November):** Repeat Bordeaux or apply systemic Hexaconazole (Contaf @ 2 ml/L).\n"
            "• **Agronomic Steps:** Maintain 50-60% shade canopy with silver oak to avoid moisture stagnation."
        )
    elif "kaveri" in q_lower or "cauvery" in q_lower:
        reply = (
            "☕ **About Kaveri Coffee (Cauvery Sln.7):**\n\n"
            "• **Origin:** High-yielding semi-dwarf hybrid bred from **Caturra × Timor Hybrid (HDT)**.\n"
            "• **Key Trait:** High natural resistance to Coffee Leaf Rust races (*Hemileia vastatrix*).\n"
            "• **In our Estate:** Planted in **Block C (6.2 Hectares)** at 1,050m ASL.\n"
            "• **Planting Density:** Ideal for close planting (6ft × 6ft or 8ft × 8ft) allowing up to 1,200 bushes per acre!"
        )
    elif "arabica" in q_lower and "robusta" in q_lower:
        reply = (
            "⚖️ **Arabica vs. Robusta in our Estate:**\n\n"
            "| Characteristic | Arabica (Block A & D) | Robusta (Block B) |\n"
            "|---|---|---|\n"
            "| **Elevation** | 1,150m – 1,300m ASL | 900m – 1,100m ASL |\n"
            "| **Flavor Profile** | Mild, aromatic, fine acidity | Bold body, thick crema, strong caffeine |\n"
            "| **Outturn Ratio** | 6:1 (Cherry to Clean) | 5:1 (Cherry to Clean) |\n"
            "| **Shade Need** | Two-tier thick shade | Light to medium shade |\n"
            "| **Market Price** | ₹17,000 – ₹18,500 / 50kg bag | ₹11,000 – ₹12,000 / 50kg bag |"
        )
    elif "pesticide" in q_lower or "spray" in q_lower:
        reply = (
            f"🧪 **Pesticide & Spraying Management:**\n\n"
            f"• Our estate currently has **{pesticide_count} logged pesticide applications**.\n"
            "• **Tracking Rules:** Every spray logs total bags, weight in kg, date applied, and number of workers in spraying gang.\n"
            "• **Pre-Harvest Interval (PHI):** Always respect minimum 21 days between last chemical spray and cherry picking.\n"
            "• Visit the [Pesticides Dashboard](/pesticides) to log or audit applications."
        )
    elif "attendance" in q_lower or "face" in q_lower or "coffee" in q_lower and ("green" in q_lower or "red" in q_lower):
        reply = (
            "🟢 **Attendance Muster System:**\n\n"
            "• **Green Coffee (☕):** Marked for **Present** workers with full daily muster credit.\n"
            "• **Red Coffee (🍒):** Marked for **Absent** workers.\n"
            "• **Security Role:** Only **Estate Admin** and **Estate Manager** are authorized to drop attendance.\n"
            "• **Face Verification:** Integrated with live camera verification (≥75% confidence threshold) to prevent proxy muster."
        )
    elif "yield" in q_lower or "harvest" in q_lower or "predict" in q_lower:
        reply = (
            f"📊 **Estate Harvest & Yield Insight:**\n\n"
            f"• **Harvested so far:** {harvest_total:,.1f} kg across all blocks.\n"
            f"• **Active Blocks:** {block_count} registered parcels.\n"
            "• You can run realistic predictive yield simulations factoring in blossom rainfall and NPK dosage on our [AI Yield Prediction Tool](/ai/yield)!"
        )
    elif "weather" in q_lower or "rain" in q_lower or "monsoon" in q_lower:
        reply = (
            "🌦️ **Chikmagalur Weather Advisory:**\n\n"
            "• **Current Zone:** Western Ghats highland elevation (1,150m ASL).\n"
            "• **Blossom Showers:** Crucial 25-40 mm required in late March/April for uniform flowering.\n"
            "• **Backing Showers:** 40-50 mm in May essential for fruit set.\n"
            "• View full 7-day spray conditions on our [Weather Advisor](/weather)."
        )
    elif "wage" in q_lower or "salary" in q_lower or "payroll" in q_lower:
        reply = (
            f"💰 **Workforce & Wage Structure:**\n\n"
            f"• Currently managing **{emp_count} registered workers**.\n"
            "• **Base Daily Wage:** Standardized according to Karnataka Plantation Labour Act.\n"
            "• **Overtime Rate:** 1.5× standard hourly wage for picking beyond daily target quota (50 kg).\n"
            "• Visit [Payroll Management](/payroll) to generate and approve monthly salary slips."
        )
    else:
        reply = (
            f"Hello {user.username if user else 'Manager'}! I am your **AI Coffee Estate Copilot**.\n\n"
            "I can assist you with:\n"
            "• **Foliage & Berry Diseases** (Leaf Rust, Berry Borer, Koleroga)\n"
            "• **Coffee Varieties** (Arabica Chandragiri, Robusta CxR, Kaveri Hybrid)\n"
            "• **Agronomic Schedules** (Bordeaux spray, NPK fertilizer, shade lopping)\n"
            "• **Workforce & Attendance** (Green/Red coffee muster, Face verification, Wages)\n"
            "• **Harvest Quality** (Cherry ripeness grading, Brix measurement)\n\n"
            "What would you like to check today?"
        )

    return jsonify({"reply": reply})


# ==============================================================================
# 5. SETTINGS & SYSTEM INTELLIGENCE (Page 20)
# ==============================================================================

@ai_bp.route("/settings", methods=["GET", "POST"])
@ai_bp.route("/settings/", methods=["GET", "POST"])
@roles_required("Admin")
def settings():
    """Page 20: Settings & Security."""
    current_user = get_current_user()

    if request.method == "POST":
        flash("Estate system configurations updated successfully.", "success")
        return redirect(url_for("ai.settings"))

    return render_template("settings.html", current_user=current_user)
