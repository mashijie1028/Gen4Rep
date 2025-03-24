import os
import csv
from PIL import Image
import torch
from tqdm import tqdm
import json
from transformers import SiglipProcessor, SiglipModel, SiglipImageProcessor, SiglipTokenizer



def benchmark_model(processor, tokenizer, model, benchmark_dir, device="cpu"):

    image_dir = os.path.join(benchmark_dir, 'MLLM_VLM Images')
    csv_file = os.path.join(benchmark_dir, 'Questions.csv')

    csv_outfile = open('Prediction_Results_SigLIP_224', 'w', newline='')
    csv_writer = csv.writer(csv_outfile)
    csv_writer.writerow(['qid1', 'qid2', 'pred1', 'pred2', 'gt1', 'gt2', 'q1score', 'q2score'])  # header

    categories = [
        'Orientation and Direction', 'Presence of Specific Features', 
        'State and Condition', 'Quantity and Count', 
        'Positional and Relational Context', 'Color and Appearance',
        'Structural Characteristics', 'Texts',
        'Viewpoint and Perspective'
    ]

    pair_accuracies = {category: 0 for category in categories}
    num_pairs = 0
    
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for i, row in tqdm(enumerate(reader)):
            qid1, qtype1, statement1 = row
        
            # Get next row for the pair
            row = next(reader, None)
            if not row:
                break
            qid2, qtype2, statement2 = row
            
            qid1, qid2 = int(qid1), int(qid2)
            
            img1 = Image.open(os.path.join(image_dir, qtype1, f'{qid1}.jpg'))
            img2 = Image.open(os.path.join(image_dir, qtype1, f'{qid2}.jpg'))

            text1 = 'a photo of ' + statement1
            text2 = 'a photo of ' + statement2

            text1 = tokenizer(
                text1,
                truncation=True,
                return_length=False,
                return_overflowing_tokens=False,
                padding="max_length",
                return_tensors="pt",
            )["input_ids"].to(device)
            text2 = tokenizer(
                text2,
                truncation=True,
                return_length=False,
                return_overflowing_tokens=False,
                padding="max_length",
                return_tensors="pt",
            )["input_ids"].to(device)

            img1 = processor.preprocess(img1, return_tensors='pt')['pixel_values'].to(device)
            img2 = processor.preprocess(img2, return_tensors='pt')['pixel_values'].to(device)
            imgs = torch.cat((img1, img2), dim=0)

            with torch.no_grad():
                model.eval().float()

                outputs1 = model(input_ids=text1, pixel_values=imgs)
                logits_per_image1, logits_per_text1 = outputs1.logits_per_image, outputs1.logits_per_text
                outputs2 = model(input_ids=text2, pixel_values=imgs)
                logits_per_image2, logits_per_text2 = outputs2.logits_per_image, outputs2.logits_per_text
                
                probs1 = logits_per_text1.softmax(dim=-1).cpu().numpy()
                probs2 = logits_per_text2.softmax(dim=-1).cpu().numpy()

            img1_score1 = probs1[0][0]
            img1_score2 = probs2[0][0]
            
            pred1 = "img1" if img1_score1 > 0.5 else "img2"
            pred2 = "img1" if img1_score2 > 0.5 else "img2"

            gt1 = "img1" if qid1 % 2 == 1 else "img2"
            gt2 = "img1" if qid2 % 2 == 1 else "img2"

            csv_writer.writerow([qid1, qid2, pred1, pred2, gt1, gt2, img1_score1, img1_score2])
                
            current_category = categories[num_pairs // 15]
            if pred1 == gt1 and pred2 == gt2:
                pair_accuracies[current_category] += 1
            num_pairs += 1
            
        csv_outfile.close()

    # Calculate percentage accuracies
    Category_Score_List = []
    
    for category in pair_accuracies:
        pair_accuracies[category] = (pair_accuracies[category] / (num_pairs // len(categories))) * 100
        Category_Score_List.append(pair_accuracies[category])
        
    pair_accuracies['average_score'] = sum(Category_Score_List)/len(Category_Score_List)

    return pair_accuracies


def official_evaluation(processor, tokenizer, clip_model, model_name, benchmark_dir, device):
    
    with torch.no_grad():
        clip_model.eval()

        results_siglip = {f'{model_name}': benchmark_model(processor, tokenizer, clip_model, benchmark_dir, device)}

        # Merge results
        results = {**results_siglip}

        # Convert results to format suitable for star plot
        categories = results[list(results.keys())[0]].keys()
        data = {'Categories': list(categories)}
        for model in list(results_siglip.keys()):
            data[model] = [results[model][category] for category in categories]

        return results


if __name__ == "__main__":

    BENCHMARK_DIR = 'YOUR_MMVP_VLM_PATH'

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vision_tower_name = f'SigLIP/siglip-so400m-patch14-224'

    vision_tower = SiglipModel.from_pretrained(vision_tower_name, device_map=device)
    image_processor = SiglipImageProcessor.from_pretrained(vision_tower_name)
    tokenizer = SiglipTokenizer.from_pretrained(vision_tower_name)

    results = official_evaluation(image_processor, tokenizer, vision_tower, vision_tower_name, BENCHMARK_DIR, device)
    print(results)
