from polycli.agents.prompts import Prompter

def test_prompter_superforecaster():
    prompter = Prompter()
    prompt = prompter.superforecaster("Question?", "Description", ["Yes", "No"])
    assert "Superforecaster" in prompt
    assert "Question?" in prompt
    assert "Yes, No" in prompt

def test_prompter_one_best_trade():
    prompter = Prompter()
    prompt = prompter.one_best_trade("Prediction", ["Yes", "No"], [0.5, 0.5])
    assert "top trader" in prompt
    assert "Prediction" in prompt
    assert "['Yes', 'No']" in prompt
