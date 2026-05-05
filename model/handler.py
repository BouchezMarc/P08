import numpy as np
import pandas as pd
# import optuna
# import mlflow
# import mlflow.sklearn
# import mlflow.lightgbm
# import matplotlib.pyplot as plt

from lightgbm.sklearn import LGBMClassifier
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    fbeta_score,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from sklearn.model_selection import StratifiedKFold
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import EditedNearestNeighbours


class ModelHandler:
    def __init__(self, model, param_grid, use_smote=False, use_enn=False, smote_params=None, enn_params=None, stratify=True, preprocessor=None, n_splits=5):
        self.model = model
        self.param_grid = param_grid
        self.use_smote = use_smote
        self.use_enn = use_enn
        self.smote_params = smote_params or {'sampling_strategy': 'auto', 'random_state': 42}
        self.enn_params = enn_params or {'sampling_strategy': 'majority'}
        self.stratify = stratify
        self.n_splits = n_splits
        self.metrics = {'precision': [], 'recall': [], 'f1': [], 'roc_auc': [], 'fbeta_2': [], 'fbeta_5': []}
        self.best_params = None
        self.preprocessor = preprocessor
        self.pipeline = None
        self.optimal_threshold = None
        self.threshold_results = None

    def build_pipeline(self):
        steps = []
        if self.preprocessor:
            steps.append(('prep', self.preprocessor))
        if self.use_smote:
            smote = SMOTE(**self.smote_params)
            steps.append(('smote', smote))
        if self.use_enn:
            enn = EditedNearestNeighbours(**self.enn_params)
            steps.append(('enn', enn))
        steps.append(('model', self.model))
        self.pipeline = ImbPipeline(steps)

    # def objective(self, trial, X_train, y_train):
    #     params = {}
    #     for param_name, param_values in self.param_grid.items():
    #         if isinstance(param_values, list):
    #             params[param_name] = trial.suggest_categorical(param_name, param_values)
    #         elif isinstance(param_values, tuple) and len(param_values) == 2:
    #             if param_name in ['n_estimators', 'max_depth', 'num_leaves']:
    #                 params[param_name] = trial.suggest_int(param_name, param_values[0], param_values[1])
    #             else:
    #                 params[param_name] = trial.suggest_float(param_name, param_values[0], param_values[1])
    #         elif isinstance(param_values, tuple) and len(param_values) == 3:
    #             params[param_name] = trial.suggest_float(param_name, param_values[0], param_values[1], log=True)

    #     model_params = {f"model__{k}": v for k, v in params.items()}
    #     self.pipeline.set_params(**model_params)

    #     mlflow.log_params(params)

    #     skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=42)
    #     auc_scores = []
    #     precision_scores = []
    #     recall_scores = []
    #     f1_scores = []
    #     fbeta2_scores = []
    #     fbeta5_scores = []
    #     cost_scores = []
    #     threshold = 0.5

    #     for train_idx, val_idx in skf.split(X_train, y_train):
    #         X_train_fold, X_val_fold = X_train.iloc[train_idx], X_train.iloc[val_idx]
    #         y_train_fold, y_val_fold = y_train.iloc[train_idx], y_train.iloc[val_idx]

    #         self.pipeline.fit(X_train_fold, y_train_fold)
    #         y_prob = self.pipeline.predict_proba(X_val_fold)[:, 1]
    #         y_pred = (y_prob >= threshold).astype(int)

    #         auc_scores.append(roc_auc_score(y_val_fold, y_prob))
    #         report = classification_report(y_val_fold, y_pred, output_dict=True)
    #         precision_scores.append(report['macro avg']['precision'])
    #         recall_scores.append(report['macro avg']['recall'])
    #         f1_scores.append(report['macro avg']['f1-score'])
    #         fbeta2_scores.append(fbeta_score(y_val_fold, y_pred, beta=2))
    #         fbeta5_scores.append(fbeta_score(y_val_fold, y_pred, beta=5))
    #         cost_scores.append(self.compute_business_cost(y_val_fold, y_pred))

    #     metrics = {
    #         'roc_auc': np.mean(auc_scores),
    #         'precision': np.mean(precision_scores),
    #         'recall': np.mean(recall_scores),
    #         'f1': np.mean(f1_scores),
    #         'fbeta_2': np.mean(fbeta2_scores),
    #         'fbeta_5': np.mean(fbeta5_scores),
    #         'cost': np.mean(cost_scores),
    #         'threshold': threshold,
    #     }

    #     mlflow.log_metrics(metrics)
    #     return metrics['roc_auc']

    # def optuna_search(self, X_train, y_train, n_trials=50):
    #     study = optuna.create_study(direction='maximize')

    #     def objective_wrapper(trial):
    #         with mlflow.start_run(run_name=f"trial_{trial.number}", nested=True):
    #             result = self.objective(trial, X_train, y_train)
    #             mlflow.log_metric('auc_trial', result)
    #             mlflow.log_param('trial_number', trial.number)
    #             return result

    #     study.optimize(objective_wrapper, n_trials=n_trials)
    #     self.best_params = study.best_params

    #     self.build_pipeline()
    #     model_params = {f"model__{k}": v for k, v in self.best_params.items()}
    #     self.pipeline.set_params(**model_params)

    #     # if isinstance(self.model, LGBMClassifier):
    #     #     mlflow.lightgbm.log_model(self.pipeline.named_steps['model'], 'lgbm_model')
    #     # else:
    #     #     mlflow.sklearn.log_model(self.pipeline, 'model')

    def train_model(self, X_train, y_train):
        skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=42)
        fold_metrics = {'precision': [], 'recall': [], 'f1': [], 'roc_auc': [], 'fbeta_2': [], 'fbeta_5': []}

        for train_idx, val_idx in skf.split(X_train, y_train):
            X_train_fold, X_val_fold = X_train.iloc[train_idx], X_train.iloc[val_idx]
            y_train_fold, y_val_fold = y_train.iloc[train_idx], y_train.iloc[val_idx]

            self.pipeline.fit(X_train_fold, y_train_fold)
            y_val_pred = self.pipeline.predict(X_val_fold)
            y_val_prob = self.pipeline.predict_proba(X_val_fold)[:, 1]

            report = classification_report(y_val_fold, y_val_pred, output_dict=True)
            fold_metrics['precision'].append(report['macro avg']['precision'])
            fold_metrics['recall'].append(report['macro avg']['recall'])
            fold_metrics['f1'].append(report['macro avg']['f1-score'])
            fold_metrics['fbeta_2'].append(fbeta_score(y_val_fold, y_val_pred, beta=2))
            fold_metrics['fbeta_5'].append(fbeta_score(y_val_fold, y_val_pred, beta=5))
            fold_metrics['roc_auc'].append(roc_auc_score(y_val_fold, y_val_prob))

        self.metrics = {key: np.mean(val) for key, val in fold_metrics.items()}
        return self.metrics

    def evaluate_model(self, X_test, y_test):
        y_test_pred = self.pipeline.predict(X_test)
        y_test_prob = self.pipeline.predict_proba(X_test)[:, 1]

        report = classification_report(y_test, y_test_pred, output_dict=True)
        self.metrics['precision'] = report['macro avg']['precision']
        self.metrics['recall'] = report['macro avg']['recall']
        self.metrics['f1'] = report['macro avg']['f1-score']
        self.metrics['fbeta_2'] = fbeta_score(y_test, y_test_pred, beta=2)
        self.metrics['fbeta_5'] = fbeta_score(y_test, y_test_pred, beta=5)
        self.metrics['roc_auc'] = roc_auc_score(y_test, y_test_prob)

        cm = confusion_matrix(y_test, y_test_pred)
        # disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=self.pipeline.classes_)
        # disp.plot()
        # plt.show()

        return self.metrics

    def compute_business_cost(self, y_true, y_pred):
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        return 10 * fn + 1 * fp

    def optimize_threshold(self, X_val, y_val, thresholds=None, plot=True):
        if thresholds is None:
            thresholds = np.arange(0.1, 0.91, 0.01)

        y_prob = self.pipeline.predict_proba(X_val)[:, 1]
        costs = []
        metrics_list = []

        for t in thresholds:
            y_pred = (y_prob >= t).astype(int)
            cost = self.compute_business_cost(y_val, y_pred)
            costs.append(cost)

            metrics = {
                'threshold': t,
                'cost': cost,
                'precision': classification_report(y_val, y_pred, output_dict=True)['macro avg']['precision'],
                'recall': classification_report(y_val, y_pred, output_dict=True)['macro avg']['recall'],
                'f1': classification_report(y_val, y_pred, output_dict=True)['macro avg']['f1-score'],
                'fbeta_2': fbeta_score(y_val, y_pred, beta=2),
                'fbeta_5': fbeta_score(y_val, y_pred, beta=5),
                'roc_auc': roc_auc_score(y_val, y_prob),
            }
            metrics_list.append(metrics)

        self.threshold_results = metrics_list
        costs_array = np.array(costs)
        optimal_idx = np.argmin(costs_array)
        self.optimal_threshold = thresholds[optimal_idx]

        # if plot:
        #     plt.figure(figsize=(8, 5))
        #     plt.plot(thresholds, costs, marker='o', label='Business Cost')
        #     plt.axvline(self.optimal_threshold, color='red', linestyle='--', label=f'Optimal threshold={self.optimal_threshold:.2f}')
        #     plt.xlabel('Threshold')
        #     plt.ylabel('Business Cost (10*FN + 1*FP)')
        #     plt.title('Business Cost vs Classification Threshold')
        #     plt.legend()
        #     plt.grid(True)
        #     plt.show()

        return self.optimal_threshold

    def evaluate_with_optimal_threshold(self, X_test, y_test):
        y_prob = self.pipeline.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= self.optimal_threshold).astype(int)

        metrics = {
            'threshold': self.optimal_threshold,
            'cost': self.compute_business_cost(y_test, y_pred),
            'precision': classification_report(y_test, y_pred, output_dict=True)['macro avg']['precision'],
            'recall': classification_report(y_test, y_pred, output_dict=True)['macro avg']['recall'],
            'f1': classification_report(y_test, y_pred, output_dict=True)['macro avg']['f1-score'],
            'fbeta_2': fbeta_score(y_test, y_pred, beta=2),
            'fbeta_5': fbeta_score(y_test, y_pred, beta=5),
            'roc_auc': roc_auc_score(y_test, y_prob),
        }
        return metrics
