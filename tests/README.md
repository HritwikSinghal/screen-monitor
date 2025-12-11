# Running the tests

To run these tests, you need to have Pytest installed in your environment. You can create a new virtual environment using `pyenv` and `pipenv`, then install the required dependencies:

```bash
# Create a new virtual environment with pyenv
python -m venv myenv
# Activate the virtual environment
source myenv/bin/activate

# Install pipenv (if not already installed)
pip install pipenv
# Create a new Pipfile for your project
pipenv sync --dev
```

Add `pytest` to the `[dev-packages]` section of your `Pipfile`, then run:

```bash
pipenv install
```

Once you have installed all the dependencies, navigate to the root directory of this project and run the following command:

```bash
pytest tests/
```

This will execute all the test cases in the `tests` directory.

### Test Environment

The tests are designed to work with OpenCV 4.x and NumPy. Make sure you have these libraries installed before running the tests.

### Test Cases

The tests cover various scenarios, including:

* Finding a target image in a screen
* Not finding a target image in a screen
* Threshold-based matching (both low and high thresholds)
* Empty target image
* Empty screen

Each test case is designed to verify a specific aspect of the `check_image_presence` function.