# # Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# # SPDX-License-Identifier: MIT-0

# import yaml
# import os
# import unittest
# import aws_cdk as core
# import aws_cdk.assertions as assertions
# from pipeline.pipeline_stack import PipelineStack


# class TestPipelineStack(unittest.TestCase):

#     # Get data from config file and convert to dict
#     config_file_path = "./configs/deploy-config.yaml"
#     with open(config_file_path, 'r', encoding="utf-8") as f:
#         config = yaml.load(f, Loader=yaml.SafeLoader)

#     def setUp(self):
#         app = core.App()
#         self.stack = PipelineStack(
#             app, "TestPipelineStack",
#             env=core.Environment(
#                 account=os.getenv('CDK_DEFAULT_ACCOUNT'),
#                 region=os.getenv('CDK_DEFAULT_REGION')
#             ),
#             config=self.config
#         )

#     def test_stack_creation(self):
#         self.assertIsInstance(self.stack, PipelineStack)
#         self.assertEqual(len(self.stack.node.children), 1)  # Assuming only one construct in the stack

#     def test_pipeline_stages(self):
#         self.assertEqual(len(self.stack.pipeline.stages), 5)  # Assuming there are two stages in the pipeline

#         stage_names = [stage.stage_name for stage in self.stack.pipeline.stages]
#         self.assertIn("Source", stage_names)
#         self.assertIn("Build", stage_names)
#         self.assertIn("UpdatePipeline", stage_names)
#         self.assertIn("Assets", stage_names)
#         self.assertIn("Deploy-Application", stage_names)

# if __name__ == '__main__':
#     unittest.main()
