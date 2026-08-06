#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { BuzzBuddyStack } from '../lib/buzzbuddy-stack';

const app = new cdk.App();
new BuzzBuddyStack(app, 'BuzzBuddyStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-east-2',
  },
});
