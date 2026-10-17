# TransImage

Cross-platform image viewer written in Python using Tkinter and Pillow.

## Getting Started

### Prerequisites
- Python 3.x
- Tkinter (usually included with Python)
- Pillow

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/TransImage.git
   cd TransImage
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

1. Sync dependencies:
   ```bash
   uv sync
   ```

2. Run the application:
   ```bash
   uv run transimage
   ```

### Running Tests

```bash
uv run pytest
```

## Features
- Open and display images across platforms (Windows, macOS, Linux)
- Maintain aspect ratio and fit the image to the window
- Bindings for opening files (`Ctrl+O` on Windows/Linux, `Cmd+O` on macOS)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request to improve this project.
