from discord.ext import commands
from discord.ext import tasks
import ssl
import re
import requests
from bs4 import BeautifulSoup as bs
import urllib.request
from operator import itemgetter
import concurrent.futures
import asyncio
from datetime import datetime
import os

now = datetime.now()

bot = commands.Bot(command_prefix='!')

token = ''
hdr = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

rank_scoring = {
    'able': 0,
    'proficient': 0,
    'distinguished': 0.5,
    'respected': 2,
    'master': 4,
    'renowned': 7,
    'grand-master': 9,
    'legendary': 12,
    'ultimate': 20
}

exp_scoring = {
    'novice': 6,
    'neophyte': 5,
    'apprentice': 4,
    'narrow': 3,
    'broad': 2,
    'solid': 1.8,
    'weighty': 1.5,
    'expert': 1.4,
    'paragon': 1.2,
    'illustrious': 1.1,
    'sublime': 0.9,
    'revered': 0.8,
    'exalted': 0.75,
    'transcendent': 0.7
}
cached = {}
flag_counts = {}
enemy_flag_counts = {}
old_jobbers = 0
old_enemy_jobbers = 0
our_bots = []
enemy_bots = []


def strip_standing_data(puzzle):
    puzzle = puzzle.split('/')
    puzzle = puzzle[1].lower()
    return puzzle


def strip_exp_data(exp):
    exp = exp.split('/')
    exp = exp[0].lower()
    return exp


# 'type' is for whether parsing a crew or a pirate.
# 'userequest' defaults to None unless we set it to a value when calling the function
# in which case we use the requests library instead of urllib
def parse(type, data, userequest=None):
    if type == 'crew':
        URL = 'http://emerald.puzzlepirates.com/yoweb/crew/info.wm?crewid=' + str(data)
    if type == 'pirate':
        URL = 'http://emerald.puzzlepirates.com/yoweb/pirate.wm?classic=false&target=' + str(data)
    if userequest is not None:
        res = requests.get("https://emerald.puzzlepirates.com/yoweb/crew/info.wm?crewid=" + str(data))
        soup = bs(res.text, "html.parser")
        return soup
    req = urllib.request.Request(URL, headers=hdr)
    r = urllib.request.urlopen(req).read()
    soup = bs(r, 'html.parser')
    return soup


def find_change(old, new):
    change = int(new) - int(old)
    if change != 0:
        if change > 0:
            return "+" + str(change)  # Purely for visual formatting
        return change
    else:
        return 0


def scrape(crewname):
    global old_jobbers
    global old_enemy_jobbers
    global crew_name
    soup = parse('crew', crewname, True)
    crew_name = soup.find("b").get_text()
    try:
        jobber_num = soup.find(string="Jobbing Pirate:").find_next(string="Jobbing Pirate:").find_next().get_text()
        jobber_num = jobber_num.strip()
    except AttributeError:  # Handles the exception if there are no jobbers in the crew.
        if crewname == id:
            return crew_name, 0, 0
        else:
            return crew_name, 0, 0
    if crewname == id:  # Check which crew is currently being parsed and set the associated variables
        change = find_change(old_jobbers, jobber_num)
        old_jobbers = jobber_num
        return crew_name, jobber_num, change

    else:
        change = find_change(old_enemy_jobbers, jobber_num)
        old_enemy_jobbers = jobber_num
        return crew_name, jobber_num, change


def get_jobber_names(id):
    soup = parse('crew', id)
    try:
        pirates_list = soup.find(src='/yoweb/images/crew-jobbing.png').find_parent('tr').find_parent(
            'tr').find_all_next('a')
        del (pirates_list[-1])
        names_list = []
        for i in pirates_list:
            names_list.append(i.string)
        return names_list
    except AttributeError:
        pass


def bot_check(pirate_soup, flag):
    data = pirate_soup.get_text()
    data = data.split('Piracy Skills')[1]
    data = data.split('Carousing Skills')[0]
    data = data.split()
    no_arch = [x for x in data if "archipelago" not in x]
    no_arch = [x for x in data if "/" in x]
    sailing = str(no_arch[0])
    rigging = str(no_arch[1])
    carpentry = str(no_arch[2])
    patching = str(no_arch[3])
    bilging = str(no_arch[4])
    sailing_exp = strip_exp_data(sailing)
    sailing = strip_standing_data(sailing)
    carpentry_exp = strip_exp_data(carpentry)
    carpentry = strip_standing_data(carpentry)
    rigging_exp = strip_exp_data(rigging)
    rigging = strip_standing_data(rigging)
    patching_exp = strip_exp_data(patching)
    patching = strip_standing_data(patching)
    bilging_exp = strip_exp_data(bilging)
    bilging = strip_standing_data(bilging)
    rank_score = (rank_scoring[rigging] * exp_scoring[rigging_exp]) + (
            rank_scoring[patching] * exp_scoring[patching_exp]) + (
                         rank_scoring[bilging] * exp_scoring[bilging_exp])
    if exp_scoring[sailing_exp] >= 4:
        rank_score = rank_score * 2
    elif exp_scoring[sailing_exp] <= 2:
        rank_score = rank_score * 0.8
    if rank_scoring[sailing] >= 2:
        rank_score = rank_score * 0.65
    if exp_scoring[carpentry_exp] >= 4:
        rank_score = rank_score * 2
    elif exp_scoring[carpentry_exp] <= 2:
        rank_score = rank_score * 0.9
    if rank_scoring[carpentry] >= 4:
        rank_score = rank_score * 0.75
    rank_score = round(rank_score, 2)
    bot_percent = (rank_score / 28) * 100
    if flag == 'Independent':
        bot_percent = bot_percent * 1.2
    if (rank_scoring[rigging] >= 7) and (rank_scoring[patching] >= 7) and (rank_scoring[bilging] >= 7):
        bot_percent = bot_percent * 2
    bot_percent = round(bot_percent, 2)
    return bot_percent


def return_flag_us(pirate):
    global our_bots
    global cached
    try:
        if pirate not in cached:
            pirate_soup = parse('pirate', pirate)
            try:
                flag = pirate_soup.find('a', href=re.compile('^/yoweb/flag')).string
            except:
                flag = 'Independent'
            cached[pirate] = flag
            is_bot = bot_check(pirate_soup, flag)
            if is_bot > 50:
                if pirate in enemy_bots:
                    enemy_bots.remove(pirate)
                our_bots.append(pirate.string)
        else:
            flag = cached[pirate]
        global flag_counts
        if flag in flag_counts:
            flag_counts[flag] += 1
        if flag not in flag_counts:
            flag_counts[flag] = 1


    except AttributeError:  # catches the error if we try get the flags for a crew with not jobbers
        pass


def return_flag_enemy(pirate):
    global enemy_bots
    global cached
    try:
        if pirate not in cached:
            enemy_pirate_soup = parse('pirate', pirate)
            try:
                flag = enemy_pirate_soup.find('a', href=re.compile('^/yoweb/flag')).string
            except:
                flag = 'Independent'
            cached[pirate] = flag
            is_bot = bot_check(enemy_pirate_soup, flag)
            if is_bot > 50:
                if pirate in our_bots:
                    our_bots.remove(pirate)
                enemy_bots.append(pirate.string)
        else:
            flag = cached[pirate]
        global enemy_flag_counts

        if flag in enemy_flag_counts:
            enemy_flag_counts[flag] += 1
        if flag not in enemy_flag_counts:
            enemy_flag_counts[flag] = 1

    except AttributeError:  # catches exception if threading tries to get the flag of an empty list
        pass


@tasks.loop(minutes=1)
async def count(ctx):
    us = scrape(id)  # Will return a tuple of 3 values, crew_name, jobber count and change.
    them = scrape(enemy_id)
    if us[2] != 0:
        await ctx.send(f"{us[0]} has {us[1]} jobbers.  ({us[2]}).")
    else:
        await ctx.send(f"{us[0]} has {us[1]} jobbers.")
    if them[2] != 0:
        await ctx.send(f"{them[0]} has {them[1]} jobbers.  ({them[2]}).")
    else:
        await ctx.send(f"{them[0]} has {them[1]} jobbers.")
    if int(us[1]) > int(them[1]):
        diff = int(us[1]) - int(them[1])
        await ctx.send(f"*Outjobbing by {diff}*")
    elif int(them[1]) > int(us[1]):
        diff = int(them[1]) - int(us[1])
        await ctx.send(f"*Being outjobbed by {diff}*")
    else:
        await ctx.send("*Jobbing even*")
    await ctx.send("------")
    await asyncio.sleep(60)


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


@bot.command(name='setid')
async def setid(ctx, arg1, arg2: int):
    global id
    global enemy_id
    if arg1 == 'us':
        id = arg2
        us = scrape(id)
        await ctx.send(f'Our crew: {us[0]}')
        names_list = get_jobber_names(id)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
                executor.map(return_flag_us, names_list)
        except TypeError:
            pass
        return id
    if arg1 == 'enemy':
        enemy_id = arg2
        them = scrape(enemy_id)
        await ctx.send(f'Enemy crew: {them[0]}')
        enemy_names_list = get_jobber_names(enemy_id)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as enemy_executor:
                enemy_executor.map(return_flag_enemy, enemy_names_list)
        except TypeError:
            pass
        return enemy_id


@bot.command(name='count')
async def count_start(ctx):
    count.start(ctx)


@bot.command(name='stop')
async def count_stop(ctx):
    count.cancel()
    await ctx.send('Count stopped.')


@bot.command(name='flags')
async def flags(ctx):
    global flag_counts
    global enemy_flag_counts
    names_list = get_jobber_names(id)
    enemy_names_list = get_jobber_names(enemy_id)
    jobber_list = []
    enemy_jobber_list = []
    flag_counts = {}
    enemy_flag_counts = {}

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
            executor.map(return_flag_us, names_list)
    except TypeError:
        pass
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as enemy_executor:
            enemy_executor.map(return_flag_enemy, enemy_names_list)
    except TypeError:
        pass
    for key, value in sorted(flag_counts.items(), key=itemgetter(1), reverse=True):
        jobber_list.append(str(key) + ": " + str(value))
    for key, value in sorted(enemy_flag_counts.items(), key=itemgetter(1), reverse=True):
        enemy_jobber_list.append(str(key) + ": " + str(value))
    await ctx.send("**Our Jobbers: " + str(sum(flag_counts.values())) + "**")
    await ctx.send('\n'.join(jobber_list))
    await ctx.send("**Enemy Jobbers: " + str(sum(enemy_flag_counts.values())) + "**")
    await ctx.send('\n'.join(enemy_jobber_list))


@bot.command(name='bots')
async def bots(ctx):
    global our_bots
    global enemy_bots
    names_list = get_jobber_names(id)
    enemy_names_list = get_jobber_names(enemy_id)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
            executor.map(return_flag_us, names_list)
    except TypeError:
        pass
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as enemy_executor:
            enemy_executor.map(return_flag_enemy, enemy_names_list)
    except TypeError:
        pass
    if len(our_bots) != 0:  # Formatting for if there are no likely bots in either crew.
        our_bots_clean = ', '.join(our_bots)
        us = scrape(id)
        our_total_bots = round(len(our_bots)/len(names_list) * 100, 2)
        await ctx.send(f"{us[0]} likely bots {our_total_bots}%:")
        await ctx.send(our_bots_clean)
    else:
        await ctx.send('No bots in friendly crew.')
    if len(enemy_bots) != 0:
        enemy_bots_clean = ', '.join(enemy_bots)
        them = scrape(enemy_id)
        enemy_total_bots = round(len(enemy_bots) / len(enemy_names_list) * 100, 2)
        await ctx.send(f"{them[0]} likely bots {enemy_total_bots}%:")
        await ctx.send(enemy_bots_clean)
    else:
        await ctx.send('No bots in enemy crew.')

@bot.command(name='complain')
async def bots(ctx):
    try:
        global enemy_bots
        complaint_list = []
        for bot in enumerate(enemy_bots):
            complaint_list.append('/complain ' + bot[1] + ' botting')
        await ctx.send('\n'.join(complaint_list))
    except TypeError:
        pass
        await ctx.send('No bots to complain')
@bot.command(name='info')
async def info(ctx, arg1: int):
    global flag_counts
    id = arg1
    us = scrape(id)
    names_list = get_jobber_names(id)
    await ctx.send(f'{us[0]} ({len(names_list)}) jobbers:')
    jobber_list = []
    flag_counts = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
            executor.map(return_flag_us, names_list)
    except TypeError:
        pass
    for key, value in sorted(flag_counts.items(), key=itemgetter(1), reverse=True):
        jobber_list.append(str(key) + ": " + str(value))
    await ctx.send('\n'.join(jobber_list))
    if len(our_bots) != 0:  # Formatting for if there are no likely bots in either crew.
        our_bots_clean = ', '.join(our_bots)
        us = scrape(id)
        our_total_bots = round(len(our_bots)/len(names_list) * 100, 2)
        await ctx.send(f"{us[0]} likely bots {our_total_bots}%:")
        await ctx.send(our_bots_clean)
    else:
        await ctx.send(f'No bots in {us[0]}.')
bot.run(token)
