"""SAM's tests. They run offline: every outside service (the map, Wikipedia, the AI model) is replaced by a stand-in.

Run from the SAM_Frontend folder:
    python -m unittest discover -s tests -v
"""

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SAM_DATA_DIR"] = tempfile.mkdtemp(prefix="sam-tests-")
for key in ("NVIDIA_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "APPLE_CLIENT_ID", "SAM_PUBLIC_URL"):
    os.environ.pop(key, None)

import sam_ai  # noqa: E402
from assistants import code_translator, concepts, guardrails  # noqa: E402
from services import geo, places, richtext, wikipedia  # noqa: E402

HOME = {"lat": 37.3794, "lon": -122.0813, "label": "Mountain View, CA"}


def fake_geocode(text):
    return HOME if "94040" in text else {}


def fake_nearby(phrase, lat, lon, radius):
    kinds = {"animal shelter": ("amenity", "animal_shelter"), "food bank": ("amenity", "food_bank"), "library": ("amenity", "library"),
             "tennis": ("leisure", "pitch"), "cricket": ("shop", "mobile_phone")}
    category, kind = kinds.get(phrase, ("amenity", "x"))
    return [{"id": f"osm:n{len(phrase)}{i}", "name": f"{phrase.title()} {i}", "category": category, "type": kind,
             "lat": lat + 0.01 * i, "lon": lon + 0.01 * i, "miles": round(0.8 * i, 1), "address": f"{i} Main St", "town": "Mountain View",
             "website": "https://example.org" if i == 1 else "", "hours": "Mo-Fr 09:00-17:00; Sa 10:00-14:00" if i == 1 else "",
             "sports": [phrase] if category == "leisure" else [], "facility": "", "members_only": False} for i in (1, 2, 3)]


def fake_wikipedia(topic, count=2):
    return [{"title": f"{topic} (Wikipedia)", "url": "https://en.wikipedia.org/wiki/X", "text": f"About {topic}.", "source": "Wikipedia"}] if topic else []


class Guardrails(unittest.TestCase):
    """The rules that stop SAM handing over answers."""

    def test_spots_requests_for_answers_and_finished_work(self):
        cases = {
            "Can you just give me the answer to my algebra homework?": "answer",
            "Solve 2x + 6 = 14": "answer",
            "What is 15% of 80?": "answer",
            "Which one is correct?\nA) mitochondria\nB) nucleus\nC) ribosome": "answer",
            "Write my essay on the causes of World War 1": "write_it",
            "write a function that reverses a string": "write_it",
            "Summarize chapter 3 of To Kill a Mockingbird": "write_it",
            "How do I write a thesis statement?": "concept",
            "Help me understand photosynthesis": "concept",
            "Why did the Roman empire fall?": "concept",
            "what does this code do: x = 5": "concept",
            "Find soccer leagues near me": "near_me",
            "How do I manage my time during finals week?": "life",
            "I want to kill myself": "crisis",
        }
        for message, kind in cases.items():
            with self.subTest(message=message):
                self.assertEqual(guardrails.inspect(message).kind, kind)

    def test_finds_the_unknown(self):
        self.assertEqual(guardrails.inspect("Solve 2x + 6 = 14").variable, "x")
        self.assertEqual(guardrails.inspect("how do I solve 3a - 4 = 11?").variable, "a")

    def test_rewrite_wraps_flagged_messages_in_coaching(self):
        verdict = guardrails.inspect("Solve 2x + 6 = 14")
        sent = guardrails.rewrite("Solve 2x + 6 = 14", verdict)
        self.assertIn("Do not give them the answer", sent)
        self.assertEqual(guardrails.rewrite("Help me understand photosynthesis", guardrails.inspect("Help me understand photosynthesis")),
                         "Help me understand photosynthesis")

    def test_review_rejects_replies_that_give_the_answer_away(self):
        verdict = guardrails.inspect("Solve 2x + 6 = 14")
        self.assertIn("it gives a value for x", guardrails.review("Subtract 6 and divide by 2, so x = 4. Got it?", verdict))
        self.assertIn("it states an answer", guardrails.review("The answer is 4. Make sense?", verdict))
        self.assertIn("it doesn't ask the student a question", guardrails.review("Subtract 6 from both sides.", verdict))
        self.assertEqual(guardrails.review("Subtract 6 from both sides. What do you get?", verdict), [])
        essay = guardrails.inspect("write my essay on WW1")
        self.assertIn("it contains a finished paragraph", guardrails.review(("word " * 100) + "?", essay))

    def test_follow_ups_keep_being_coached(self):
        follow_up = guardrails.carry_over(guardrails.inspect("so what is x?"), "so what is x?", ["Solve 2x + 6 = 14"])
        self.assertTrue(follow_up.coach)
        self.assertIn("it gives a value for x", guardrails.review("x = 4", follow_up, "so what is x?"))
        # A value the student worked out themselves may be confirmed.
        mine = guardrails.carry_over(guardrails.inspect("is it 4?"), "is it 4?", ["Solve 2x + 6 = 14"])
        self.assertEqual(guardrails.review("Yes! x = 4 is right.", mine, "is it 4?"), [])
        # A new subject is a new question.
        self.assertFalse(guardrails.carry_over(guardrails.inspect("Help me understand photosynthesis"), "Help me understand photosynthesis",
                                               ["Solve 2x + 6 = 14"]).coach)

    def test_built_in_coaching_passes_its_own_review(self):
        for message in ("Solve 2x + 6 = 14", "What is 15% of 80?", "write my essay", "write a function that sorts a list"):
            verdict = guardrails.inspect(message)
            self.assertEqual(guardrails.review(guardrails.coach_reply(verdict), verdict), [], message)


@mock.patch.object(wikipedia, "introductions", fake_wikipedia)
class ConceptHelper(unittest.TestCase):
    """One chat turn, with and without the AI model."""

    prefs = {"age": "15", "loc": "94040", "sports": [], "vol": [], "playsSports": "no", "sportOther": "", "volOther": ""}

    def test_crisis_gets_the_safety_reply_without_the_model(self):
        with mock.patch.object(sam_ai, "complete") as model:
            reply = concepts.ask("I want to kill myself", [], self.prefs)
        model.assert_not_called()
        self.assertIn("988", reply["text"])

    def test_demo_mode_coaches_and_cites(self):
        reply = concepts.ask("Solve 2x + 6 = 14", [], self.prefs)
        self.assertEqual(reply["mode"], "demo")
        self.assertTrue(reply["guard"])
        self.assertNotRegex(reply["text"], r"x\s*=\s*4")
        self.assertTrue(reply["sources"])

    def test_a_leaking_model_is_retried_then_replaced(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}), mock.patch.object(sam_ai, "complete", return_value="Easy: x = 4.") as model:
            reply = concepts.ask("Solve 2x + 6 = 14", [], self.prefs)
        self.assertEqual(model.call_count, 2)  # The first reply was rejected, so SAM asked again
        sent = model.call_args_list[0].args[0]
        self.assertIn("Do not give them the answer", sent[-1]["content"])  # The model never saw the bare request
        self.assertEqual(reply["text"], guardrails.coach_reply(guardrails.inspect("Solve 2x + 6 = 14")))

    def test_a_good_model_reply_is_shown_with_deep_dives(self):
        answer = "Plants make sugar from light [1]. What do you think the leaf needs?\n\n### Deep dive: Chlorophyll\nIt absorbs light."
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}), mock.patch.object(sam_ai, "complete", return_value=answer):
            reply = concepts.ask("Help me understand photosynthesis", [], self.prefs)
        self.assertEqual(reply["mode"], "model")
        self.assertEqual(reply["deep_dives"], [{"title": "Chlorophyll", "body": "It absorbs light."}])
        self.assertTrue(reply["sources"][0]["cited"])


class RichText(unittest.TestCase):
    def test_markdown_is_rendered_safely(self):
        html = str(richtext.render("**Bold** <script>alert(1)</script> [ok](https://a.org) [bad](javascript:alert(1)) [1]",
                                   cite=lambda n: '<b class="cite">1</b>' if n == 1 else None))
        self.assertIn("<strong>Bold</strong>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('<a href="https://a.org"', html)
        self.assertNotIn('href="javascript', html)
        self.assertIn('<b class="cite">1</b>', html)

    def test_lists_and_code(self):
        html = str(richtext.render("1. one\n2. two\n\n```\nx = '<b>'\n```"))
        self.assertIn("<ol><li>one</li><li>two</li></ol>", html)
        self.assertIn("<pre><code>x = &#x27;&lt;b&gt;&#x27;</code></pre>", html)


class OpeningHours(unittest.TestCase):
    def test_reads_common_formats(self):
        hours = "Mo-Fr 09:00-17:00; Sa 10:00-14:00"
        self.assertEqual(places.pretty_hours(hours), "Mon–Fri 9 am to 5 pm; Sat 10 am to 2 pm")
        self.assertEqual(places.open_status(hours, 5, "morning"), "open")
        self.assertEqual(places.open_status(hours, 6, "any"), "closed")
        self.assertEqual(places.open_status(hours, 2, "evening"), "closed")
        self.assertEqual(places.open_status('"by appointment"', 2, "any"), None)
        self.assertEqual(places.pretty_hours("24/7"), "Open 24 hours")

    def test_distance(self):
        self.assertAlmostEqual(geo.miles_between(37.3794, -122.0813, 37.4419, -122.1430), 5.6, delta=0.3)


class CodeTranslator(unittest.TestCase):
    def test_explains_python_line_by_line(self):
        result = code_translator.explain("total = 0\nfor n in range(3):\n    total += n\nprint(total)", "python")
        self.assertTrue(result["ok"])
        texts = [row["text"] for row in result["lines"]]
        self.assertIn("counts up from 0", texts[1])
        self.assertEqual(texts[2], "Adds `n` to `total`.")
        self.assertIn("    INCREASE total BY n", result["pseudocode"])

    def test_explains_curly_brace_languages(self):
        result = code_translator.explain("for (let i = 0; i < 10; i++) {\n  if (i % 2 === 0) continue;\n}", "javascript")
        self.assertIn("counting `i` from `0` up to, but not including, `10`", result["lines"][0]["text"])
        self.assertIn("`i` is even", result["lines"][1]["text"])

    def test_made_up_languages(self):
        pirate, problem = code_translator.clean_language("PirateScript", {"print": "shout", "if": "maybe", "else": "otherwise"})
        self.assertEqual(problem, "")
        result = code_translator.explain('maybe 1:\n    shout("maybe")  # shout', "python", custom=pirate)
        self.assertEqual(result["mirror"]["code"], 'if 1:\n    print("maybe")  # shout')  # Words in quotes and comments stay
        self.assertIn("Shows", result["lines"][1]["text"])
        self.assertIsNone(code_translator.clean_language("Python", {"print": "a", "if": "b", "else": "c"})[0])
        self.assertIsNone(code_translator.clean_language("Mine", {"print": "if", "if": "b", "else": "c"})[0])

    def test_uses_the_model_when_connected(self):
        reply = json.dumps({"summary": "Prints hi.", "lines": [{"n": 1, "text": "Prints the word hi."}], "pseudocode": "DISPLAY hi"})
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}), mock.patch.object(sam_ai, "complete", return_value=reply):
            result = code_translator.explain('print("hi")', "python")
        self.assertEqual((result["engine"], result["lines"][0]["text"], result["pseudocode"]), ("model", "Prints the word hi.", "DISPLAY hi"))

    def test_limits(self):
        self.assertFalse(code_translator.explain("", "python")["ok"])
        self.assertFalse(code_translator.explain("x = 1\n" * 200, "python")["ok"])
        self.assertFalse(code_translator.explain("x", "klingon")["ok"])


@mock.patch.object(geo, "geocode", fake_geocode)
@mock.patch.object(places, "nearby", fake_nearby)
@mock.patch.object(wikipedia, "introductions", fake_wikipedia)
class Pages(unittest.TestCase):
    """The website, from sign-up to each assistant."""

    def setUp(self):
        import app
        self.app = app
        self.client = app.app.test_client()
        name = f"t{len(os.listdir(os.environ['SAM_DATA_DIR']))}{id(self) % 10000}"
        self.client.post("/login", data={"mode": "signup", "name": "Test", "username": name, "email": f"{name}@example.com",
                                         "password": "password123", "consent": "1"})
        self.client.post("/confirm", data={"action": "yes"})

    def survey(self, loc="94040"):
        return self.client.post("/survey", data={"age": "15", "loc": loc, "gender": "female", "playsSports": "yes", "sports": ["Tennis"],
                                                  "vol": ["Animal shelters"], "radius": "5"})

    def test_survey_finds_the_place_and_leads_home(self):
        self.assertIn("couldn’t find", self.survey("nowhere at all").get_data(as_text=True))
        response = self.survey()
        self.assertTrue(response.headers["Location"].endswith("/home"))
        page = self.client.get("/home").get_data(as_text=True)
        self.assertIn("Mountain View, CA", page)
        for link in ("/volunteer", "/sports", "/chat", "/code", "/plan"):
            self.assertIn(f'href="{link}"', page)

    def test_volunteer_and_sports_finders(self):
        self.survey()
        page = self.client.get("/volunteer?loc=94040&radius=5&category=animals&slot=any").get_data(as_text=True)
        self.assertIn("Animal Shelter 1", page)
        self.assertIn("Usually 2–3 hour shifts", page)
        self.assertIn("Visit website to sign up", page)
        page = self.client.get("/sports?loc=94040&radius=5&sport=Tennis&sport=Cricket&group=any").get_data(as_text=True)
        self.assertIn("Tennis 1", page)
        self.assertNotIn("Cricket 1", page)  # A phone shop called "Cricket" isn't a place to play
        self.assertIn("Tennis clinics near Mountain View, CA", page)

    def test_saving_to_my_plan(self):
        self.survey()
        page = self.client.get("/volunteer?loc=94040&category=animals").get_data(as_text=True)
        token = re.search(r'name="item" value="([^"]+)"', page).group(1)
        day = (date.today() + timedelta(days=2)).isoformat()
        saved = self.client.post("/plan/toggle", data={"item": token, "day": day, "slot": "morning"}, headers={"X-Requested-With": "fetch"})
        self.assertEqual(saved.get_json(), {"ok": True, "saved": True})
        self.assertIn("Animal Shelter 1", self.client.get("/plan").get_data(as_text=True))
        calendar = self.client.get("/plan.ics").get_data(as_text=True)
        self.assertIn("SUMMARY:Animal Shelter 1", calendar)
        self.assertIn("T100000", calendar)  # Morning starts at 10 am
        self.assertEqual(self.client.post("/plan/toggle", data={"item": "made-up"}).status_code, 400)

    def test_concept_helper_answers_without_reloading(self):
        self.survey()
        reply = self.client.post("/chat/send", data={"message": "Solve 2x + 6 = 14"}, headers={"X-Requested-With": "fetch"}).get_json()
        self.assertTrue(reply["ok"])
        self.assertIn("SAM is coaching instead of answering", reply["html"])

    def test_code_translator_and_languages(self):
        self.survey()
        reply = self.client.post("/code/explain", data={"code": "print(1)", "language": "python"}, headers={"X-Requested-With": "fetch"}).get_json()
        self.assertIn("Shows `1` on the screen.".replace("`1`", "<code>1</code>"), reply["html"])
        made = self.client.post("/code/languages", data={"name": "Pirate", "word_print": "shout", "word_if": "maybe", "word_else": "otherwise"})
        self.assertIn("custom:Pirate", made.headers["Location"])
        page = self.client.post("/code", data={"code": 'shout("hi")', "language": "custom:Pirate"}).get_data(as_text=True)
        self.assertIn("The same code in Python", page)


if __name__ == "__main__":
    unittest.main()
