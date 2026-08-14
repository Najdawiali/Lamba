"""
Populate bilingual name_ar, name_en, description_ar, description_en for all GlobalItem records.
"""

import asyncio
import re
from sqlalchemy import select
from app.database import async_session
from app.models.global_item import GlobalItem

# Translation dictionary for seed/common items
TRANSLATIONS = {
    # Tea & Coffee
    "Green Tea - Matcha Organic": ("شاي ماتشا أخضر عضوي", "Green Tea - Matcha Organic", "مسحوق شاي ماتشا ياباني أخضر فاخر للاحتفالات.", "Premium Japanese matcha green tea powder, ceremonial grade."),
    "Arabic Coffee - Dark Roast": ("قهوة عربية - تحميص غامق", "Arabic Coffee - Dark Roast", "قهوة عربية سعودية تقليدية محمصة بالهيل.", "Traditional Saudi Arabic coffee, dark roasted with cardamom."),
    "Turkish Coffee - Medium": ("قهوة تركية - تحميص وسط", "Turkish Coffee - Medium", "قهوة تركية محمصة تحميصاً وسطياً ومطحونة بعناية.", "Medium roast Turkish coffee, finely ground."),
    "Earl Grey Tea": ("شاي إيرل غراي", "Earl Grey Tea", "شاي إيرل غراي كلاسيكي بنكهة البرغموت العطرية.", "Classic Earl Grey with bergamot essence."),
    "Chamomile Tea - Organic": ("شاي بابونج عضوي", "Chamomile Tea - Organic", "شاي بابونج عضوي مهدئ ومريح للأعصاب.", "Soothing organic chamomile herbal tea."),
    "Matcha Powder - Culinary": ("مسحوق ماتشا للطبخ", "Matcha Powder - Culinary", "مسحوق ماتشا عضوي للحلويات والمشروبات واللاتيه.", "Culinary grade matcha for lattes and baking."),
    "Matcha Latte Powder": ("مسحوق شاي ماتشا لاتيه", "Matcha Latte Powder", "خلطة ماتشا لاتيه سريعة التحضير بالحليب.", "Instant matcha latte mix with milk."),
    "Matcha Green Tea Powder": ("مسحوق شاي ماتشا فاخر", "Matcha Green Tea Powder", "ماتشا احتفالية نقية لتعزيز التركيز.", "Ceremonial grade matcha for focus."),

    # Honey, Spreads, Oils
    "Honey - Sidr Premium": ("عسل سدر فاخر", "Honey - Sidr Premium", "عسل سدر يمني نقي خام وغير مصفى.", "Pure Yemeni Sidr honey, raw and unfiltered."),
    "Dates - Medjool Premium": ("تمر مجدول فاخر", "Dates - Medjool Premium", "تمر مجدول فاخر حبات كبيرة وطازجة من المدينة المنورة.", "Large, soft Medjool dates from Al-Madinah."),
    "Olive Oil - Extra Virgin": ("زيت زيتون بكر ممتاز", "Olive Oil - Extra Virgin", "زيت زيتون بكر ممتاز معصور على البارد من جبال الأردن.", "Cold-pressed extra virgin olive oil from Jordan."),
    "Black Seed Oil": ("زيت حبة البركة النقي", "Black Seed Oil", "زيت حبة البركة الأصلي المعصور على البارد.", "Pure cold-pressed black seed oil (Nigella sativa)."),
    "Coconut Oil - Raw Virgin": ("زيت جوز هند بكر خام", "Coconut Oil - Raw Virgin", "زيت جوز هند بكر معصور على البارد.", "Cold-pressed raw virgin coconut oil."),
    "Lavender Essential Oil": ("زيت الخزامى (اللافندر) العطري", "Lavender Essential Oil", "زيت لافندر عطري نقي للاسترخاء والعناية.", "Pure lavender essential oil for aromatherapy."),
    "Tahini - Sesame Paste": ("طحينة سمسم فاخرة", "Tahini - Sesame Paste", "طحينة سمسم نقي 100% ناعمة وغنية.", "Pure sesame tahini, smooth and creamy."),
    "Almond Butter - Raw": ("زبدة لوز خام", "Almond Butter - Raw", "زبدة لوز عضوية خام خالية من السكر المضاف.", "Raw organic almond butter, no added sugar."),

    # Spices & Seeds
    "Saffron - Iranian Grade 1": ("زعفران إيراني درجة أولى", "Saffron - Iranian Grade 1", "خيوط زعفران إيراني فاخر بنكهة ولون رائعين.", "Premium Iranian saffron threads, intense aroma."),
    "Cardamom Pods - Green": ("حبوب هيل أخضر", "Cardamom Pods - Green", "حبوب هيل أخضر كاملة غواتيمالية ممتازة.", "Whole green cardamom pods from Guatemala."),
    "Pistachios - Roasted Salted": ("فستق حلبي محمص ومملح", "Pistachios - Roasted Salted", "فستق حلبي محمص ومملح فاخر مقرمش ولذيذ.", "Premium Antep pistachios, roasted and salted."),
    "Cashews - Raw Organic": ("كاجو نيء عضوي", "Cashews - Raw Organic", "كاجو نيء عضوي ممتاز للوجبات الخفيفة والطبخ.", "Organic raw cashews, perfect for snacking."),
    "Cinnamon Sticks - Ceylon": ("عيدان قرفة سيلانية", "Cinnamon Sticks - Ceylon", "عيدان قرفة سيلانية أصلية حلوة وعطرية.", "True Ceylon cinnamon sticks, delicate and sweet."),
    "Sumac - Ground": ("سماق بلدي مطحون", "Sumac - Ground", "سماق بلدي مطحون طازج بنكهة ليمونية مميزة.", "Ground sumac with tangy lemony flavor."),
    "Chia Seeds - Organic": ("بذور الشيا العضوية", "Chia Seeds - Organic", "بذور شيا عضوية غنية بالأوميغا 3 والألياف.", "Organic chia seeds, high in omega-3 and fiber."),
    "Turmeric Powder - Organic": ("مسحوق كركم عضوي", "Turmeric Powder - Organic", "كركم عضوي مطحون غني بالكركمين.", "Ground organic turmeric with high curcumin."),

    # Grocery Essentials
    "White Sugar": ("سكر أبيض ناعم", "White Sugar", "سكر أبيض ناعم ومكرر للشاي والحلويات.", "Fine white granulated sugar."),
    "Basmati Rice - Premium": ("أرز بسمتي فاخر", "Basmati Rice - Premium", "أرز بسمتي هندي فاخر طويل الحبة.", "Premium long-grain Indian basmati rice."),
    "All-Purpose Flour": ("طحين متعدد الاستخدامات", "All-Purpose Flour", "طحين أبيض متعدد الاستخدامات للخبز والمعجنات.", "White all-purpose flour for baking."),
    "Powdered Milk - Full Fat": ("حليب بودرة كامل الدسم", "Powdered Milk - Full Fat", "حليب مجفف كامل الدسم للمشروبات والحلويات.", "Full fat powdered milk for drinks and cooking."),
    "Red Lentils": ("عدس أحمر مجروش", "Red Lentils", "عدس أحمر مجروش فاخر للشوربات والأطباق الشعبية.", "Split red lentils for soups and dals."),
    "Spaghetti Pasta": ("معكرونة سباغيتي", "Spaghetti Pasta", "معكرونة سباغيتي إيطالية فاخرة من القمح القاسي.", "Italian spaghetti pasta, durum wheat."),
    "Tomato Paste": ("معجون طماطم مركز", "Tomato Paste", "معجون طماطم مركز طبيعي 100% للطهي.", "Concentrated tomato paste for cooking."),
    "Apple Cider Vinegar": ("خل تفاح طبيعي خام", "Apple Cider Vinegar", "خل تفاح طبيعي غير مفلتر مع الأم.", "Organic raw apple cider vinegar with mother."),
    "Chickpea Flour": ("طحين حمص مطحون", "Chickpea Flour", "طحين حمص فاخر للفلافل والمخبوزات.", "Ground chickpea flour for hummus and falafel."),
    "Fine Bulgur Wheat": ("برغل ناعم", "Fine Bulgur Wheat", "برغل ناعم للتبولة والكبة والمأكولات الشرقية.", "Fine bulgur wheat for kibbeh and tabbouleh."),
    "Green Freekeh": ("فريكة خضراء مدخنة", "Green Freekeh", "فريكة خضراء مدخنة للطبخ التقليدي.", "Smoked green freekeh for traditional dishes."),
    "Green Olives - Pickled": ("زيتون أخضر مخلل", "Green Olives - Pickled", "زيتون أخضر بلدي أردني مخلل بنكهة غنية.", "Pickled Jordanian green olives."),
    "Condensed Milk - Sweetened": ("حليب مكثف محلى", "Condensed Milk - Sweetened", "حليب مكثف محلى للحلويات والمشروبات.", "Sweetened condensed milk for desserts."),
    "Tortilla Wraps - Whole Wheat": ("خبز تورتيلا قمح كامل", "Tortilla Wraps - Whole Wheat", "رقائق خبز تورتيلا مصنوعة من طحين القمح الكامل.", "Whole wheat tortilla wraps."),
    "Soy Sauce - Japanese": ("صلصة صويا يابانية", "Soy Sauce - Japanese", "صلصة صويا طبيعية التخمير للطبخ والتتبيل.", "Naturally brewed Japanese soy sauce."),
    "Cornmeal - Fine": ("طحين ذرة ناعم", "Cornmeal - Fine", "طحين ذرة ناعم للمعجنات والخبز.", "Fine cornmeal for baking and polenta."),
    "Vermicelli Noodles": ("شعيرية رفيعة", "Vermicelli Noodles", "شعيرية رفيعة ممتازة للشوربات والأرز بالشعيرية.", "Thin vermicelli for soups and rice."),
}

ARABIC_RE = re.compile(r'[\u0600-\u06FF]')

async def populate():
    async with async_session() as session:
        result = await session.execute(select(GlobalItem))
        items = result.unique().scalars().all()
        updated = 0

        for item in items:
            name = item.name or ""
            desc = item.description or ""
            changed = False

            # Check translation dictionary first
            if name in TRANSLATIONS:
                name_ar, name_en, desc_ar, desc_en = TRANSLATIONS[name]
                if not item.name_ar:
                    item.name_ar = name_ar
                    changed = True
                if not item.name_en:
                    item.name_en = name_en
                    changed = True
                if not item.description_ar:
                    item.description_ar = desc_ar
                    changed = True
                if not item.description_en:
                    item.description_en = desc_en
                    changed = True
            else:
                # Check if name is Arabic
                is_arabic = bool(ARABIC_RE.search(name))
                if is_arabic:
                    if not item.name_ar:
                        item.name_ar = name
                        changed = True
                    if not item.description_ar and desc:
                        item.description_ar = desc
                        changed = True
                else:
                    if not item.name_en:
                        item.name_en = name
                        changed = True
                    if not item.description_en and desc:
                        item.description_en = desc
                        changed = True
                    # If name_ar is still empty, default to name as fallback
                    if not item.name_ar:
                        item.name_ar = name
                        changed = True
                    if not item.description_ar and desc:
                        item.description_ar = desc
                        changed = True

            if changed:
                updated += 1

        await session.commit()
        print(f"Successfully updated translations for {updated} items in database.")

if __name__ == "__main__":
    asyncio.run(populate())
