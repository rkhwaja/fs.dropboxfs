#!/usr/bin/env python

from json import dump
from os import environ

from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from pyperclip import copy

def Run():
	oauthFlow = DropboxOAuth2FlowNoRedirect(consumer_key=environ['DROPBOX_APP_KEY'], consumer_secret=environ['DROPBOX_APP_SECRET'], token_access_type='offline') # noqa: S106

	approvalUrl = oauthFlow.start()

	copy(approvalUrl)
	print(f'Visit {approvalUrl} (copied to clipboard) and copy the authorization code')
	code = input('Enter authorization code: ')

	oauthResult = oauthFlow.finish(code)
	print(oauthResult)
	with open(environ['DROPBOX_CREDENTIALS_PATH'], 'w', encoding='utf-8') as f:
		dump({'access_token': oauthResult.access_token, 'refresh_token': oauthResult.refresh_token, 'app_key': environ['DROPBOX_APP_KEY'], 'app_secret': environ['DROPBOX_APP_SECRET']}, f)

if __name__ == '__main__':
	Run()
