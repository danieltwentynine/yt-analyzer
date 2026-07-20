import requests
from bs4 import BeautifulSoup


def print_secret_message(url):

    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    all_rows = table.find_all("tr")

    header = [c.get_text().strip().lower() for c in all_rows[0].find_all(["td", "th"])]
    x_col = next(i for i, h in enumerate(header) if h.startswith("x"))
    y_col = next(i for i, h in enumerate(header) if h.startswith("y"))
    char_col = next(i for i in range(len(header)) if i not in (x_col, y_col))

    entries = []
    for row in all_rows[1:]:
        cells = [c.get_text().strip() for c in row.find_all("td")]
        if len(cells) < 3 or not cells[x_col].isdigit():
            continue
        x = int(cells[x_col])
        y = int(cells[y_col])
        char = cells[char_col]
        entries.append((x, char, y))

    max_x = max(x for x, _, _ in entries)
    max_y = max(y for _, _, y in entries)

    grid = [[" "] * (max_x + 1) for _ in range(max_y + 1)]
    for x, char, y in entries:
        grid[y][x] = char

    for row in grid:
        print("".join(row))

if __name__ == "__main__":
    doc_url = "https://docs.google.com/document/d/e/2PACX-1vSvM5gDlNvt7npYHhp_XfsJvuntUhq184By5xO_pA4b_gCWeXb6dM6ZxwN8rE6S4ghUsCj2VKR21oEP/pub"
    print_secret_message(doc_url)