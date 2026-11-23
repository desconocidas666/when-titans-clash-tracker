import unittest
from bs4 import BeautifulSoup

from scraper import GRADE_RE, extract_records


class GradeParsingTests(unittest.TestCase):
    def test_supported_grade_formats(self):
        cases = {
            "Popular Comics 96 (FR/G 1.5)": "FR/G 1.5",
            "Action Comics 303 (FR/G 1.5)": "FR/G 1.5",
            "Action Comics 267 (G/VG 3.0)": "G/VG 3.0",
            "Popular Comics 87 (VG/FN 5.0)": "VG/FN 5.0",
            "Fantastic Four 237 (FN/VF 7.0)": "FN/VF 7.0",
            "Fantastic Four 214 (G- 1.8)": "G- 1.8",
            "Action Comics 296 (FN+ 6.5)": "FN+ 6.5",
            "Popular Comics 93 (VF 8.0)": "VF 8.0",
            "Fantastic Four Annual 18 (NM- 9.2)": "NM- 9.2",
            "DC Comics Presents 1 (CGC 6.0)": "CGC 6.0",
            "CGC graded example (CBCS 9.8)": "CBCS 9.8",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                match = GRADE_RE.search(title)
                self.assertIsNotNone(match)
                self.assertEqual(f"{match.group('label').upper()} {match.group('score')}", expected)

    def test_sold_listing_is_kept_without_condition(self):
        html = """
        <div class="product">
          <h3>Popular Comics 68 (VG- 3.5)</h3>
          <p>SOLD</p>
          <p>Price: £35.00</p>
          <p>Notes: Oct 1941.</p>
        </div>
        """
        records = extract_records(BeautifulSoup(html, "html.parser"), "https://example.test/category.html")
        self.assertEqual(len(records), 1)
        item = next(iter(records.values()))
        self.assertEqual(item["status"], "sold")
        self.assertEqual(item["grade"], "VG- 3.5")
        self.assertEqual(item["condition"], "")

    def test_in_stock_listing_is_kept_without_condition(self):
        html = """
        <div class="product">
          <h3>Popular Comics 49 (VG 4.0)</h3>
          <p>Price: £67.50</p>
          <p>Notes: Mar 1940.</p>
        </div>
        """
        records = extract_records(BeautifulSoup(html, "html.parser"), "https://example.test/category.html")
        self.assertEqual(len(records), 1)
        item = next(iter(records.values()))
        self.assertEqual(item["status"], "in_stock")
        self.assertEqual(item["grade"], "VG 4.0")
        self.assertEqual(item["condition"], "")

    def test_identical_copies_are_not_merged(self):
        html = """
        <div class="product">
          <h3>Jungle Action 1 (FN 6.0)</h3>
          <p>Price: £12.50</p>
          <p>Condition: FN (6.0). Copy one.</p>
        </div>
        <div class="product">
          <h3>Jungle Action 1 (FN 6.0)</h3>
          <p>Price: £12.50</p>
          <p>Condition: FN (6.0). Copy two.</p>
        </div>
        """
        records = extract_records(BeautifulSoup(html, "html.parser"), "https://example.test/category.html")
        self.assertEqual(len(records), 2)
        self.assertEqual(len({item["id"] for item in records.values()}), 2)


    def test_publication_date_is_extracted_from_notes(self):
        html = """
        <div class="product">
          <h3>Popular Comics 49 (VG 4.0)</h3>
          <p>Price: £67.50</p>
          <p>Notes: Mar 1940. Featuring Martan the Marvel Man.</p>
          <p>Condition: VG (4.0).</p>
        </div>
        """
        records = extract_records(BeautifulSoup(html, "html.parser"), "https://example.test/category.html")
        item = next(iter(records.values()))
        self.assertEqual(item["published_date"], "Mar 1940")
        self.assertTrue(item["notes"].startswith("Mar 1940."))

    def test_publication_date_supports_full_month_name(self):
        html = """
        <div class="product">
          <h3>Action Comics 1 (VG 4.0)</h3>
          <p>Price: £100.00</p>
          <p>Notes: September 1938. Classic issue.</p>
        </div>
        """
        records = extract_records(BeautifulSoup(html, "html.parser"), "https://example.test/category.html")
        item = next(iter(records.values()))
        self.assertEqual(item["published_date"], "Sep 1938")


if __name__ == "__main__":
    unittest.main()
